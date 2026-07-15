"""Import exam papers and reference answers from Word documents."""

from __future__ import annotations

import re
from pathlib import Path
from zipfile import BadZipFile

from docx import Document

from helpers.date_helper import get_now
from helpers.db_helper import get_db


EXAM_DURATION_MINUTES = 50
QUESTION_SCORES = {
    "single_choice": 2,
    "multiple_choice": 3,
    "true_false": 1,
    "short_answer": 7,
    "case_analysis": 15,
}
EXAM_SOURCE_PATTERN = "*材料进场验收标准专项考试卷*.docx"
DESKTOP_QUESTION_BANK_DIR = Path.home() / "Desktop" / "题库"
BUNDLED_QUESTION_BANK_DIR = Path(__file__).resolve().parents[1] / "docs" / "exam_sources" / "question_bank"


PAPER_TITLE_RE = re.compile(r"^第[一二三四五]套(?!.*参考答案)")
ANSWER_TOKEN_RE = re.compile(r"(\d+)\s*[.．、]\s*([A-E√×]+)")
NUMBERED_TEXT_RE = re.compile(r"^(\d+)\s*[.．、]\s*(.*)")
OPTION_RE = re.compile(r"([A-E])[.．、](.*?)(?=\s+[A-E][.．、]|$)")
BANK_OPTION_RE = re.compile(r"^([A-D])[\s.．、]+(.+)$")
BANK_ANSWER_TOKEN_RE = re.compile(r"(\d+)\s*[.．、]?\s*([A-D]+|[√×])")


def parse_exam_docx(path: Path) -> list[dict]:
    """Parse five formal exam papers from a Word document."""
    lines = _read_lines(path)
    paper_ranges = _paper_ranges(lines)
    papers = []

    for paper_number, start_index in enumerate(paper_ranges, start=1):
        end_index = paper_ranges[paper_number] if paper_number < len(paper_ranges) else len(lines)
        paper_lines = lines[start_index:end_index]
        papers.append(_parse_paper(paper_lines, paper_number))

    return papers


def parse_available_docx(path: Path) -> tuple[list[dict], str]:
    """Parse complete leading papers and return a warning for the first malformed chunk."""
    lines = _read_lines(path)
    paper_ranges = _paper_ranges(lines)
    papers = []

    for paper_number, start_index in enumerate(paper_ranges, start=1):
        end_index = paper_ranges[paper_number] if paper_number < len(paper_ranges) else len(lines)
        paper_lines = lines[start_index:end_index]
        try:
            papers.append(_parse_paper(paper_lines, paper_number))
        except ValueError as exc:
            if not papers:
                raise
            return papers, str(exc)

    return papers, ""


def get_question_bank_dir(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    for candidate in (BUNDLED_QUESTION_BANK_DIR, DESKTOP_QUESTION_BANK_DIR):
        if candidate.exists() and list(candidate.glob("*.docx")):
            return candidate
    return BUNDLED_QUESTION_BANK_DIR


def parse_question_bank_docx(path: Path) -> dict:
    """Parse a single objective-question bank document."""
    lines = _read_lines(path)
    title = lines[0] if lines else path.stem
    single_start = _find_index(lines, lambda line: line.startswith("一、单选题"), "Question bank missing single-choice section.")
    multiple_start = _find_index(lines, lambda line: line.startswith("二、多选题"), "Question bank missing multiple-choice section.")
    true_false_start = _find_index(lines, lambda line: line.startswith("三、判断题"), "Question bank missing true/false section.")
    answer_start = _find_index(lines, lambda line: line == "参考答案", "Question bank missing answers section.")

    answer_lines = lines[answer_start + 1 :]
    single_answer_start = _find_index(
        answer_lines, lambda line: line.startswith("一、单选题"), "Question bank missing single-choice answers."
    )
    multiple_answer_start = _find_index(
        answer_lines, lambda line: line.startswith("二、多选题"), "Question bank missing multiple-choice answers."
    )
    true_false_answer_start = _find_index(
        answer_lines, lambda line: line.startswith("三、判断题"), "Question bank missing true/false answers."
    )
    answers = {
        "single_choice": _parse_bank_answer_tokens(
            answer_lines[single_answer_start + 1 : multiple_answer_start]
        ),
        "multiple_choice": _parse_bank_answer_tokens(
            answer_lines[multiple_answer_start + 1 : true_false_answer_start]
        ),
        "true_false": _parse_bank_answer_tokens(answer_lines[true_false_answer_start + 1 :]),
    }

    single_questions = _parse_bank_choice_questions(
        lines[single_start + 1 : multiple_start],
        "single_choice",
        answers["single_choice"],
    )
    multiple_questions = _parse_bank_choice_questions(
        lines[multiple_start + 1 : true_false_start],
        "multiple_choice",
        answers["multiple_choice"],
    )
    true_false_questions = _parse_bank_true_false_questions(
        lines[true_false_start + 1 : answer_start],
        answers["true_false"],
    )

    questions = []
    order_no = 1
    for group in (single_questions, multiple_questions, true_false_questions):
        questions.extend(_with_order_numbers(group, order_no))
        order_no += len(group)

    expected_counts = {
        "single_choice": 30,
        "multiple_choice": 20,
        "true_false": 30,
    }
    actual_counts = {
        question_type: sum(1 for question in questions if question["question_type"] == question_type)
        for question_type in expected_counts
    }
    if actual_counts != expected_counts:
        raise ValueError(f"Question bank counts mismatch: {actual_counts}.")

    return {
        "title": title,
        "total_score": sum(question["score"] for question in questions),
        "duration_minutes": EXAM_DURATION_MINUTES,
        "questions": questions,
    }


def parse_literature_question_bank_docx(path: Path) -> dict:
    """Parse the current desktop question-bank format with inline answers/explanations."""
    lines = _read_lines(path)
    title = lines[0] if lines else path.stem
    questions: list[dict] = []
    current_type = "single_choice"
    current: dict | None = None

    def flush() -> None:
        nonlocal current
        if current and current.get("stem") and current.get("correct_answer"):
            current["order_no"] = len(questions) + 1
            current["type_order"] = sum(
                1 for item in questions if item["question_type"] == current["question_type"]
            ) + 1
            questions.append(current)
        current = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if line == title:
            continue
        if _is_literature_section_heading(line):
            flush()
            if "判断" in line:
                current_type = "true_false"
            elif "多" in line:
                current_type = "multiple_choice"
            else:
                current_type = "single_choice"
            continue

        answer = _prefixed_text(line, "答案")
        if answer is not None:
            if current:
                current["correct_answer"] = answer.replace(" ", "").upper()
            continue

        explanation = _prefixed_text(line, "解析")
        if explanation is not None:
            if current:
                current["reference_answer"] = explanation
                current["keywords"] = _keywords(explanation)
            flush()
            continue

        inline_options = _parse_options(line)
        if inline_options:
            if current is not None:
                current["options"].extend(inline_options)
            continue

        option = BANK_OPTION_RE.match(line)
        if option:
            if current is not None:
                current["options"].append({"key": option.group(1), "text": option.group(2).strip()})
            continue

        flush()
        current = _question(
            question_type=current_type,
            type_order=0,
            stem=re.sub(r"^\d+\s*[.．、]\s*", "", line).strip(),
            options=[],
            correct_answer="",
            reference_answer="",
            keywords="",
        )

    flush()
    if not questions:
        raise ValueError(f"No questions parsed from {path}")
    return {
        "title": title,
        "total_score": sum(question["score"] for question in questions),
        "duration_minutes": EXAM_DURATION_MINUTES,
        "questions": questions,
    }


def _is_literature_section_heading(line: str) -> bool:
    return bool(re.match(r"^[一二三四五六七八九十]+[、.．]", line)) and (
        "单" in line or "多" in line or "判断" in line
    )


def _prefixed_text(line: str, prefix: str) -> str | None:
    for separator in (":", "："):
        marker = prefix + separator
        if line.startswith(marker):
            return line[len(marker):].strip()
    return None


def _parse_bank_answer_tokens(lines: list[str]) -> dict[int, str]:
    answers: dict[int, str] = {}
    for line in lines:
        for number, answer in BANK_ANSWER_TOKEN_RE.findall(line):
            answers[int(number)] = answer
    return answers


def _parse_bank_choice_questions(
    lines: list[str], question_type: str, answers: dict[int, str]
) -> list[dict]:
    questions: list[dict] = []
    stem = ""
    options: list[dict] = []

    def flush() -> None:
        if not stem and not options:
            return
        type_order = len(questions) + 1
        if len(options) != 4:
            raise ValueError(
                f"Question bank {question_type} question {type_order} "
                f"expected 4 options, found {len(options)}."
            )
        correct_answer = answers.get(type_order, "")
        if not correct_answer:
            raise ValueError(f"Question bank {question_type} question {type_order} missing answer.")
        questions.append(
            _question(
                question_type=question_type,
                type_order=type_order,
                stem=stem,
                options=options.copy(),
                correct_answer=correct_answer,
            )
        )

    for line in lines:
        option_match = BANK_OPTION_RE.match(line)
        if option_match:
            options.append({"key": option_match.group(1), "text": option_match.group(2).strip()})
            continue
        flush()
        stem = line
        options = []

    flush()
    return questions


def _parse_bank_true_false_questions(lines: list[str], answers: dict[int, str]) -> list[dict]:
    questions = []
    for line in lines:
        stem = re.sub(r"^\d+\s+", "", line).strip()
        if not stem:
            continue
        type_order = len(questions) + 1
        correct_answer = answers.get(type_order, "")
        if correct_answer not in {"√", "×"}:
            raise ValueError(f"Question bank true/false question {type_order} missing answer.")
        questions.append(
            _question(
                question_type="true_false",
                type_order=type_order,
                stem=stem,
                options=[],
                correct_answer=correct_answer,
            )
        )
    return questions


def _read_lines(path: Path) -> list[str]:
    doc = Document(path)
    lines: list[str] = []
    for paragraph in doc.paragraphs:
        for line in paragraph.text.splitlines():
            stripped = line.strip()
            if stripped:
                lines.append(stripped)
    return lines


def _paper_ranges(lines: list[str]) -> list[int]:
    ranges = [
        index
        for index, line in enumerate(lines)
        if PAPER_TITLE_RE.match(line) and "参考答案" not in line
    ]
    if len(ranges) != 5:
        raise ValueError(f"Expected 5 paper chunks, found {len(ranges)}.")
    return ranges


def _parse_paper(lines: list[str], paper_number: int) -> dict:
    paper_title = lines[0] if lines else f"paper {paper_number}"
    answer_start = _find_index(
        lines,
        lambda line: "参考答案" in line,
        (
            f"Could not find reference answer section for paper "
            f"{paper_number} ({paper_title})."
        ),
    )
    question_lines = lines[:answer_start]
    answer_lines = lines[answer_start:]

    section_indexes = _question_section_indexes(question_lines, paper_number)
    answer_indexes = _answer_section_indexes(answer_lines, paper_number)
    answers = _parse_answers(answer_lines, answer_indexes)

    questions: list[dict] = []
    order_no = 1

    single_questions = _parse_choice_questions(
        question_lines[section_indexes["single"] + 1 : section_indexes["multiple"]],
        "single_choice",
        answers["single"],
    )
    questions.extend(_with_order_numbers(single_questions, order_no))
    order_no += len(single_questions)

    multiple_questions = _parse_choice_questions(
        question_lines[section_indexes["multiple"] + 1 : section_indexes["true_false"]],
        "multiple_choice",
        answers["multiple"],
    )
    questions.extend(_with_order_numbers(multiple_questions, order_no))
    order_no += len(multiple_questions)

    true_false_questions = _parse_true_false_questions(
        question_lines[section_indexes["true_false"] + 1 : section_indexes["short_answer"]],
        answers["true_false"],
    )
    questions.extend(_with_order_numbers(true_false_questions, order_no))
    order_no += len(true_false_questions)

    short_answer_questions = _parse_subjective_questions(
        question_lines[section_indexes["short_answer"] + 1 : section_indexes["case_analysis"]],
        "short_answer",
        answers["short_answer"],
    )
    questions.extend(_with_order_numbers(short_answer_questions, order_no))
    order_no += len(short_answer_questions)

    case_questions = _parse_subjective_questions(
        question_lines[section_indexes["case_analysis"] + 1 :],
        "case_analysis",
        {1: "\n".join(answers["case_analysis"].values())},
    )
    questions.extend(_with_order_numbers(case_questions, order_no))

    if len(questions) != 38:
        _raise_validation_error(
            paper_number,
            paper_title,
            "all_questions",
            "n/a",
            f"expected 38 questions, found {len(questions)}",
        )
    _validate_questions(questions, paper_number, paper_title)

    return {
        "title": paper_title,
        "total_score": 100,
        "duration_minutes": EXAM_DURATION_MINUTES,
        "questions": questions,
    }


def _question_section_indexes(lines: list[str], paper_number: int) -> dict[str, int]:
    return {
        "single": _find_index(
            lines, lambda line: "单项选择题" in line, f"Paper {paper_number} missing single-choice section."
        ),
        "multiple": _find_index(
            lines, lambda line: "多项选择题" in line, f"Paper {paper_number} missing multiple-choice section."
        ),
        "true_false": _find_index(
            lines, lambda line: "判断题" in line, f"Paper {paper_number} missing true/false section."
        ),
        "short_answer": _find_index(
            lines, lambda line: "简答题" in line, f"Paper {paper_number} missing short-answer section."
        ),
        "case_analysis": _find_index(
            lines, lambda line: "案例分析题" in line, f"Paper {paper_number} missing case-analysis section."
        ),
    }


def _answer_section_indexes(lines: list[str], paper_number: int) -> dict[str, int]:
    return {
        "single": _find_index(
            lines, lambda line: "单项选择题" in line, f"Paper {paper_number} missing single-choice answers."
        ),
        "multiple": _find_index(
            lines, lambda line: "多项选择题" in line, f"Paper {paper_number} missing multiple-choice answers."
        ),
        "true_false": _find_index(
            lines, lambda line: "判断题" in line, f"Paper {paper_number} missing true/false answers."
        ),
        "short_answer": _find_index(
            lines, lambda line: "简答题" in line, f"Paper {paper_number} missing short-answer references."
        ),
        "case_analysis": _find_index(
            lines, lambda line: "案例分析题" in line, f"Paper {paper_number} missing case-analysis references."
        ),
    }


def _parse_answers(lines: list[str], indexes: dict[str, int]) -> dict[str, dict[int, str]]:
    return {
        "single": _parse_answer_tokens(lines[indexes["single"] + 1 : indexes["multiple"]]),
        "multiple": _parse_answer_tokens(lines[indexes["multiple"] + 1 : indexes["true_false"]]),
        "true_false": _parse_answer_tokens(lines[indexes["true_false"] + 1 : indexes["short_answer"]]),
        "short_answer": _parse_numbered_blocks(
            lines[indexes["short_answer"] + 1 : indexes["case_analysis"]]
        ),
        "case_analysis": _parse_numbered_blocks(lines[indexes["case_analysis"] + 1 :]),
    }


def _parse_answer_tokens(lines: list[str]) -> dict[int, str]:
    answers: dict[int, str] = {}
    for line in lines:
        for number, answer in ANSWER_TOKEN_RE.findall(line):
            answers[int(number)] = answer
    return answers


def _parse_numbered_blocks(lines: list[str]) -> dict[int, str]:
    blocks: dict[int, list[str]] = {}
    current_number: int | None = None

    for line in lines:
        match = NUMBERED_TEXT_RE.match(line)
        if match:
            current_number = int(match.group(1))
            blocks[current_number] = [match.group(2).strip()]
        elif current_number is not None:
            blocks[current_number].append(line)

    return {
        number: "\n".join(part for part in parts if part).strip()
        for number, parts in blocks.items()
    }


def _parse_choice_questions(
    lines: list[str], question_type: str, answers: dict[int, str]
) -> list[dict]:
    questions: list[dict] = []
    stem_parts: list[str] = []

    for _, line in enumerate(lines):
        options = _parse_options(line)
        if not options:
            stem_parts.append(line)
            continue

        option_match = OPTION_RE.search(line)
        if option_match is None:
            raise ValueError(f"Could not locate options while parsing {question_type}: {line}")
        option_start = option_match.start()
        inline_stem = line[:option_start].strip()
        if inline_stem:
            stem_parts.append(inline_stem)

        type_order = len(questions) + 1
        questions.append(
            _question(
                question_type=question_type,
                type_order=type_order,
                stem="\n".join(stem_parts).strip(),
                options=options,
                correct_answer=answers.get(type_order, ""),
            )
        )
        stem_parts = []

    if stem_parts:
        raise ValueError(f"Unmatched stem while parsing {question_type}: {stem_parts[-1]}")

    return questions


def _parse_options(line: str) -> list[dict]:
    return [
        {"key": match.group(1), "text": match.group(2).strip()}
        for match in OPTION_RE.finditer(line)
    ]


def _validate_questions(questions: list[dict], paper_number: int, paper_title: str) -> None:
    expected_counts = {
        "single_choice": 16,
        "multiple_choice": 10,
        "true_false": 9,
        "short_answer": 2,
        "case_analysis": 1,
    }
    objective_types = {"single_choice", "multiple_choice", "true_false"}
    subjective_types = {"short_answer", "case_analysis"}

    for question in questions:
        question_type = question["question_type"]
        type_order = question["type_order"]

        if question_type in objective_types and not question.get("correct_answer"):
            _raise_validation_error(
                paper_number,
                paper_title,
                question_type,
                type_order,
                "missing correct_answer",
            )

        if question_type in subjective_types and not question.get("reference_answer"):
            _raise_validation_error(
                paper_number,
                paper_title,
                question_type,
                type_order,
                "missing reference_answer",
            )

        expected_option_count = {
            "single_choice": 4,
            "multiple_choice": 5,
        }.get(question_type)
        if expected_option_count is not None:
            options = question.get("options", [])
            option_keys = [option.get("key") for option in options]
            expected_option_keys = (
                ["A", "B", "C", "D"]
                if question_type == "single_choice"
                else ["A", "B", "C", "D", "E"]
            )
            if len(options) != expected_option_count:
                _raise_validation_error(
                    paper_number,
                    paper_title,
                    question_type,
                    type_order,
                    f"expected {expected_option_count} options, found {len(options)}",
                )
            for option in options:
                if not option.get("text"):
                    _raise_validation_error(
                        paper_number,
                        paper_title,
                        question_type,
                        type_order,
                        f"options: option {option.get('key', '')} has empty text",
                    )

            if option_keys != expected_option_keys:
                _raise_validation_error(
                    paper_number,
                    paper_title,
                    question_type,
                    type_order,
                    f"option keys must be {expected_option_keys}, found {option_keys}",
                )

            correct_answer = question.get("correct_answer", "")
            if question_type == "single_choice":
                if len(correct_answer) != 1 or correct_answer not in option_keys:
                    _raise_validation_error(
                        paper_number,
                        paper_title,
                        question_type,
                        type_order,
                        f"invalid correct_answer {correct_answer!r}",
                    )
            else:
                answer_letters = list(correct_answer)
                if (
                    any(letter not in option_keys for letter in answer_letters)
                    or len(set(answer_letters)) != len(answer_letters)
                ):
                    _raise_validation_error(
                        paper_number,
                        paper_title,
                        question_type,
                        type_order,
                        f"invalid correct_answer {correct_answer!r}",
                    )

        if question_type == "true_false" and question.get("correct_answer") not in {"√", "×"}:
            _raise_validation_error(
                paper_number,
                paper_title,
                question_type,
                type_order,
                f"invalid correct_answer {question.get('correct_answer')!r}",
            )

    actual_counts = {
        question_type: sum(1 for question in questions if question["question_type"] == question_type)
        for question_type in expected_counts
    }
    for question_type, expected_count in expected_counts.items():
        actual_count = actual_counts[question_type]
        if actual_count != expected_count:
            _raise_validation_error(
                paper_number,
                paper_title,
                question_type,
                "n/a",
                f"expected {expected_count} questions, found {actual_count}",
            )


def _raise_validation_error(
    paper_number: int,
    paper_title: str,
    question_type: str,
    type_order: int | str,
    detail: str,
) -> None:
    raise ValueError(
        f"paper {paper_number} ({paper_title}) {question_type} "
        f"type_order {type_order}: {detail}."
    )


def _parse_true_false_questions(lines: list[str], answers: dict[int, str]) -> list[dict]:
    return [
        _question(
            question_type="true_false",
            type_order=index + 1,
            stem=line,
            options=[],
            correct_answer=answers.get(index + 1, ""),
        )
        for index, line in enumerate(lines)
    ]


def _parse_subjective_questions(
    lines: list[str], question_type: str, reference_answers: dict[int, str]
) -> list[dict]:
    if question_type == "case_analysis":
        stem = "\n".join(lines).strip()
        reference_answer = reference_answers.get(1, "")
        return [
            _question(
                question_type=question_type,
                type_order=1,
                stem=stem,
                options=[],
                correct_answer="",
                reference_answer=reference_answer,
                keywords=_keywords(reference_answer or stem),
            )
        ]

    questions = []
    for index, line in enumerate(lines):
        reference_answer = reference_answers.get(index + 1, "")
        questions.append(
            _question(
                question_type=question_type,
                type_order=index + 1,
                stem=line,
                options=[],
                correct_answer="",
                reference_answer=reference_answer,
                keywords=_keywords(reference_answer or line),
            )
        )
    return questions


def _question(
    *,
    question_type: str,
    type_order: int,
    stem: str,
    options: list[dict],
    correct_answer: str,
    reference_answer: str = "",
    keywords: str = "",
) -> dict:
    return {
        "question_type": question_type,
        "order_no": 0,
        "type_order": type_order,
        "stem": stem,
        "options": options,
        "correct_answer": correct_answer,
        "reference_answer": reference_answer,
        "keywords": keywords,
        "score": QUESTION_SCORES[question_type],
    }


def _with_order_numbers(questions: list[dict], start: int) -> list[dict]:
    for offset, question in enumerate(questions):
        question["order_no"] = start + offset
    return questions


def _keywords(text: str) -> str:
    phrases = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    keywords: list[str] = []
    for phrase in phrases:
        for term in re.split(r"[，。；、：；（）()]", phrase):
            term = term.strip()
            if 2 <= len(term) <= 12 and term not in keywords:
                keywords.append(term)
            if len(keywords) >= 12:
                return ",".join(keywords)
    return ",".join(keywords or phrases[:1])


def _find_index(lines: list[str], predicate, error_message: str) -> int:
    for index, line in enumerate(lines):
        if predicate(line):
            return index
    raise ValueError(error_message)


# Backwards-compatible local alias for helpers and tests that expect the old name.
parse_docx = parse_exam_docx


def _connection():
    try:
        return get_db(), False
    except RuntimeError:
        import sqlite3
        import config

        conn = sqlite3.connect(config.DATABASE_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn, True


def import_exam_papers_from_docx(path: Path) -> dict:
    """Replace active formal exam papers without deleting historical records."""
    papers = parse_exam_docx(Path(path))
    conn, should_close = _connection()
    cursor = conn.cursor()

    try:
        existing_rows = cursor.execute(
            "SELECT id FROM exam_papers WHERE source_type = ?",
            ("exam",),
        ).fetchall()
        existing_ids = [row["id"] for row in existing_rows]
        archived = len(existing_ids)

        _archive_existing_exam_papers(cursor, existing_ids)
        _clear_current_exam_setting(cursor)

        inserted_ids = [insert_paper(cursor, paper, source_type="exam") for paper in papers]

        conn.commit()
        result = {"inserted": len(inserted_ids), "removed": 0}
        if archived:
            result["archived"] = archived
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        if should_close:
            conn.close()


def import_exam_papers_from_question_bank_dir(path: Path | None = None) -> dict:
    """Replace active formal papers with all .docx files from the provided question-bank directory."""
    source_dir = get_question_bank_dir(path)
    docx_files = sorted(source_dir.glob("*.docx"))
    if not docx_files:
        raise FileNotFoundError(f"No question bank .docx files found in {source_dir}")

    papers = []
    for docx_path in docx_files:
        try:
            papers.append(parse_literature_question_bank_docx(docx_path))
        except BadZipFile:
            continue
    if not papers:
        raise ValueError(f"No valid question bank .docx files found in {source_dir}")
    conn, should_close = _connection()
    cursor = conn.cursor()

    try:
        existing_rows = cursor.execute(
            "SELECT id FROM exam_papers WHERE source_type = ?",
            ("exam",),
        ).fetchall()
        existing_ids = [row["id"] for row in existing_rows]
        archived = len(existing_ids)
        _archive_existing_exam_papers(cursor, existing_ids)
        _clear_current_exam_setting(cursor)

        inserted_ids = [insert_paper(cursor, paper, source_type="exam") for paper in papers]

        conn.commit()
        return {"inserted": len(inserted_ids), "archived": archived, "removed": 0}
    except Exception:
        conn.rollback()
        raise
    finally:
        if should_close:
            conn.close()


def sync_question_bank_reference_answers(path: Path | None = None) -> dict:
    """Backfill missing question explanations from the desktop question bank."""
    source_dir = get_question_bank_dir(path)
    docx_files = sorted(source_dir.glob("*.docx"))
    if not docx_files:
        return {"updated": 0, "matched": 0, "source_files": 0}

    references: dict[tuple[str, str, str], str] = {}
    references_by_options: dict[tuple[str, str, tuple[tuple[str, str], ...]], str] = {}
    source_files = 0
    for docx_path in docx_files:
        try:
            paper = parse_literature_question_bank_docx(docx_path)
        except (BadZipFile, ValueError):
            continue
        source_files += 1
        for question in paper["questions"]:
            reference_answer = str(question.get("reference_answer") or "").strip()
            if not reference_answer:
                continue
            key = _question_reference_key(question)
            references.setdefault(key, reference_answer)
            option_key = _question_option_reference_key(question)
            if option_key:
                references_by_options.setdefault(option_key, reference_answer)

    if not references:
        return {"updated": 0, "matched": 0, "source_files": source_files}

    conn, should_close = _connection()
    try:
        rows = conn.execute(
            """
            SELECT id, question_type, stem, correct_answer, reference_answer
            FROM exam_questions
            """
        ).fetchall()
        updated = 0
        matched = 0
        for row in rows:
            key = _question_reference_key(row)
            reference_answer = references.get(key)
            if not reference_answer and references_by_options:
                option_rows = conn.execute(
                    """
                    SELECT option_key, option_text
                    FROM exam_question_options
                    WHERE question_id = ?
                    ORDER BY option_key
                    """,
                    (row["id"],),
                ).fetchall()
                reference_answer = references_by_options.get(
                    _question_option_reference_key(
                        row,
                        [{"key": option["option_key"], "text": option["option_text"]} for option in option_rows],
                    )
                )
            if not reference_answer:
                continue
            matched += 1
            current_reference = str(row["reference_answer"] or "").strip()
            if current_reference:
                continue
            conn.execute(
                "UPDATE exam_questions SET reference_answer = ? WHERE id = ?",
                (reference_answer, row["id"]),
            )
            updated += 1
        conn.commit()
        return {"updated": updated, "matched": matched, "source_files": source_files}
    except Exception:
        conn.rollback()
        raise
    finally:
        if should_close:
            conn.close()


def _question_reference_key(question) -> tuple[str, str, str]:
    stem = question["stem"] if isinstance(question, dict) else question["stem"]
    question_type = question["question_type"] if isinstance(question, dict) else question["question_type"]
    correct_answer = question["correct_answer"] if isinstance(question, dict) else question["correct_answer"]
    normalized_stem = re.sub(r"^\d+\s*[.．、]\s*", "", str(stem or "")).strip()
    normalized_stem = re.sub(r"\s+", "", normalized_stem)
    normalized_answer = str(correct_answer or "").replace(" ", "").replace("，", ",").upper()
    return (str(question_type or ""), normalized_stem, normalized_answer)


def _question_option_reference_key(question, options: list[dict] | None = None):
    question_type = question["question_type"] if isinstance(question, dict) else question["question_type"]
    correct_answer = question["correct_answer"] if isinstance(question, dict) else question["correct_answer"]
    normalized_answer = str(correct_answer or "").replace(" ", "").replace("，", ",").upper()
    if options is None:
        options = question.get("options", []) if isinstance(question, dict) else []
    option_signature = tuple(
        (
            str(option.get("key") or "").strip().upper(),
            re.sub(r"\s+", "", str(option.get("text") or "")),
        )
        for option in options
        if str(option.get("key") or "").strip()
    )
    if not option_signature:
        return None
    return (str(question_type or ""), normalized_answer, option_signature)


def ensure_exam_sources_imported() -> dict:
    """Import bundled formal exam papers only when the database has none."""
    conn, should_close = _connection()
    try:
        formal_rows = conn.execute(
            "SELECT id FROM exam_papers WHERE source_type = ? ORDER BY id",
            ("exam",),
        ).fetchall()
        existing_count = len(formal_rows)
    finally:
        if should_close:
            conn.close()

    question_bank_dir = get_question_bank_dir()

    if existing_count:
        if question_bank_dir.exists() and list(question_bank_dir.glob("*.docx")):
            sync_question_bank_reference_answers(question_bank_dir)
        return {"created": False, "paper_count": existing_count}

    if question_bank_dir.exists() and list(question_bank_dir.glob("*.docx")):
        try:
            result = import_exam_papers_from_question_bank_dir(question_bank_dir)
            return {"created": True, "paper_count": result["inserted"]}
        except ValueError:
            pass

    source_dir = Path(__file__).resolve().parents[1] / "docs" / "exam_sources"
    try:
        source_path = next(source_dir.glob(EXAM_SOURCE_PATTERN))
    except StopIteration as exc:
        raise FileNotFoundError(
            f"No exam source matching {EXAM_SOURCE_PATTERN!r} in {source_dir}"
        ) from exc

    result = import_exam_papers_from_docx(source_path)
    return {"created": True, "paper_count": result["inserted"]}


def _clear_current_exam_setting(cursor) -> None:
    cursor.execute(
        "DELETE FROM exam_settings WHERE key = ?",
        ("current_exam_paper_id",),
    )


def _archive_existing_exam_papers(cursor, paper_ids: list[int]) -> None:
    if not paper_ids:
        return

    placeholders = ",".join("?" for _ in paper_ids)
    cursor.execute(
        f"UPDATE exam_papers SET source_type = ? WHERE id IN ({placeholders})",
        ["archived_exam", *paper_ids],
    )


def insert_paper(cursor, paper: dict, source_type: str = "exam") -> int:
    """Insert one parsed paper and its questions/options."""
    cursor.execute(
        """
        INSERT INTO exam_papers (title, duration_minutes, total_score, source_type, create_time)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            paper["title"],
            paper.get("duration_minutes", EXAM_DURATION_MINUTES),
            100,
            source_type,
            get_now(),
        ),
    )
    paper_id = cursor.lastrowid

    for question in paper.get("questions", []):
        cursor.execute(
            """
            INSERT INTO exam_questions (
                paper_id, question_type, order_no, stem, correct_answer,
                reference_answer, keywords, score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paper_id,
                question["question_type"],
                question["order_no"],
                question["stem"],
                question.get("correct_answer", ""),
                question.get("reference_answer", ""),
                question.get("keywords", ""),
                question["score"],
            ),
        )
        question_id = cursor.lastrowid
        for option in question.get("options", []):
            cursor.execute(
                """
                INSERT INTO exam_question_options (question_id, option_key, option_text)
                VALUES (?, ?, ?)
                """,
                (question_id, option["key"], option["text"]),
            )

    return paper_id
