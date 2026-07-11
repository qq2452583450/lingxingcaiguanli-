from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_prod_deploy_verifies_current_exam_paper_delete_route():
    workflow = (ROOT / ".github" / "workflows" / "deploy-prod.yml").read_text(
        encoding="utf-8"
    )

    assert "/api/exam/admin/current-paper" in workflow
    assert "Method Options" in workflow
    assert "DELETE" in workflow


def test_prod_deploy_runs_sync_restart_and_verification_in_separate_ssh_steps():
    workflow = (ROOT / ".github" / "workflows" / "deploy-prod.yml").read_text(
        encoding="utf-8"
    )

    assert "name: Sync prod source" in workflow
    assert "name: Restart production service" in workflow
    assert "name: Verify production routes" in workflow
