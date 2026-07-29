from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_exam_taker_tabs_are_role_gated():
    index = (ROOT / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "exam.js").read_text(encoding="utf-8")

    assert 'class="exam-tab exam-taker-only active" data-exam-tab="practice"' in index
    assert 'class="exam-tab exam-taker-only" data-exam-tab="exam"' in index
    assert 'class="exam-tab exam-taker-only" data-exam-tab="results"' in index
    assert "document.querySelectorAll('.exam-taker-only')" in script
    assert "canTakeExam(currentUser)" in script


def test_formal_exam_pool_admin_tab_is_manager_only():
    index = (ROOT / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "exam.js").read_text(encoding="utf-8")

    assert 'class="exam-tab exam-manager-only" data-exam-tab="formalExam"' in index
    assert "loadFormalExamAdmin()" in script
    assert "formal_exam_pool" in script


def test_exam_bank_management_can_clear_current_paper():
    script = (ROOT / "static" / "js" / "exam.js").read_text(encoding="utf-8")

    assert "clearCurrentExamPaper()" in script
    assert "取消当前" in script
    assert "method: 'DELETE'" in script
