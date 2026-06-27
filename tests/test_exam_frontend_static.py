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
