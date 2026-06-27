from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_exam_center_nav_and_module_exist():
    html = read_text("index.html")

    assert 'data-module="exam"' in html
    assert "考试中心" in html
    assert 'id="examModule"' in html


def test_exam_frontend_script_is_loaded_and_routed():
    html = read_text("index.html")
    app_js = read_text("static/js/app.js")

    assert "/static/js/exam.js" in html
    assert "case 'exam': loadExamCenter(); break;" in app_js


def test_exam_role_helpers_are_present():
    exam_js = read_text("static/js/exam.js")

    assert "function canTakeExam" in exam_js
    assert "function canUseExamCenter" in exam_js
    assert "canTakeExam(user) || canManageExam(user)" in exam_js
    assert "const EXAM_TAKER_ROLES" in exam_js
    assert "const EXAM_MANAGER_ROLES" in exam_js
    for role in ("材料员", "材料审批负责人", "基地负责人"):
        assert role in exam_js
    assert "系统管理员" in exam_js
    assert "EXAM_TAKER_ROLES = ['材料员', '材料审批负责人', '基地负责人']" in exam_js
    assert "EXAM_MANAGER_ROLES = ['材料审批负责人', '系统管理员']" in exam_js
    assert "当前账号仅可管理考试，不能参加正式考试。" in exam_js


def test_exam_tabs_have_required_structure():
    html = read_text("index.html")

    assert 'class="exam-tabs"' in html
    assert 'id="examContent"' in html
    for tab_label in ("随机练习", "正式考试", "我的成绩", "题库管理", "阅卷", "成绩查询"):
        assert tab_label in html


def test_exam_js_exposes_expected_entrypoints():
    exam_js = read_text("static/js/exam.js")

    for function_name in (
        "canManageExam",
        "loadExamCenter",
        "showExamTab",
        "loadRandomPractice",
        "startCurrentExam",
        "renderExamQuestions",
        "submitExamAttempt",
        "loadMyExamResults",
        "loadExamPapersAdmin",
        "setCurrentExamPaper",
        "loadPendingReviews",
        "submitReviewScore",
        "loadAllExamResults",
    ):
        assert f"function {function_name}" in exam_js
