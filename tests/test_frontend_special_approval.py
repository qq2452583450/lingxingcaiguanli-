from pathlib import Path


def test_frontend_hides_admin_approval_for_special_inquiries():
    source = Path("static/js/app.js").read_text(encoding="utf-8")

    assert "function isSpecialApprovalInquiry" in source
    assert "applicant_username" in source
    assert "wanglihua" in source
    assert "GX" in source
    assert "canApproveInquiry(i)" in source
