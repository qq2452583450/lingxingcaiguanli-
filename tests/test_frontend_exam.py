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
    for tab_label in ("随机练习", "正式考试", "我的成绩", "题库管理", "阅卷", "成绩查询", "打卡记录"):
        assert tab_label in html
    assert 'data-exam-tab="checkins"' in html


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
        "loadCheckinRecords",
        "setCheckinFilter",
        "deleteExamAttempt",
    ):
        assert f"function {function_name}" in exam_js


def test_exam_frontend_supports_practice_feedback_and_history():
    exam_js = read_text("static/js/exam.js")

    assert "/api/exam/practice/submit" in exam_js
    assert "/api/exam/practice/history" in exam_js
    assert "/api/exam/practice/wrong" in exam_js
    assert "renderPracticeResult" in exam_js
    assert "loadPracticeHistory" in exam_js
    assert "loadWrongPracticeQuestions" in exam_js
    assert "ensureTrueFalseOptions" in exam_js
    assert "/review" in exam_js


def test_exam_practice_uses_dedicated_mobile_session_page():
    app_py = read_text("app.py")
    exam_js = read_text("static/js/exam.js")

    assert "/exam/practice-session" in app_py
    assert "exam-practice-session.html" in app_py
    assert "window.location.href = '/exam/practice-session'" in exam_js
    assert "/api/exam/practice/daily-status" in exam_js


def test_dedicated_practice_page_requests_thirty_and_shows_checkin_status():
    html = read_text("exam-practice-session.html")
    page_js = read_text("static/js/exam-practice-page.js")

    assert "/static/js/exam-practice-page.js" in html
    assert "/api/exam/practice/random?limit=30" in page_js
    assert "/api/exam/practice/submit" in page_js
    assert "/api/exam/practice/daily-status" in page_js
    assert "80%" in page_js
    assert "daily-checkin-passed" in page_js
    assert "daily-checkin-failed" in page_js


def test_dedicated_practice_page_supports_draft_save_but_formal_exam_does_not():
    page_js = read_text("static/js/exam-practice-page.js")
    exam_js = read_text("static/js/exam.js")

    assert "/api/exam/practice/draft" in page_js
    assert "savePracticeDraft" in page_js
    assert "restorePracticeDraft" in page_js
    assert "暂存" in page_js
    assert "/api/exam/attempts/${attemptId}/draft" not in exam_js
    assert "暂存" not in exam_js


def test_exam_admin_checkin_records_and_result_delete_frontend():
    exam_js = read_text("static/js/exam.js")

    assert "/api/exam/admin/checkins" in exam_js
    assert "examCheckinFilter" in exam_js
    assert "data-checkin-filter=\"missing\"" in exam_js
    assert "data-checkin-filter=\"failed\"" in exam_js
    assert "data-checkin-filter=\"passed\"" in exam_js
    assert "/api/exam/admin/attempts/" in exam_js
    assert "method: 'DELETE'" in exam_js
    assert "删除" in exam_js
