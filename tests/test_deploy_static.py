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


def test_practice_regrade_workflow_backs_up_database_and_runs_script():
    workflow = (ROOT / ".github" / "workflows" / "regrade-practice.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch" in workflow
    assert "tools\\regrade_practice_attempts.py" in workflow
    assert "--apply --backup" in workflow


def test_liu_adjustment_workflow_is_scoped_to_the_approved_operation():
    workflow = (ROOT / ".github" / "workflows" / "adjust-liu-practice.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch" in workflow
    assert "tools\\adjust_practice_records.py" in workflow
    assert "0x5218" in workflow
    assert "0x5149" in workflow
    assert "0x534E" in workflow
    assert "'2026-07-16'" in workflow
    assert "'2026-07-20'" in workflow
    assert "--apply --backup" in workflow


def test_liu_inspection_workflow_is_read_only():
    workflow = (ROOT / ".github" / "workflows" / "inspect-liu-practice.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch" in workflow
    assert "--list-sessions" in workflow
    assert "--list-eligible" in workflow
    assert "--apply" not in workflow


def test_liu_creation_workflow_previews_and_backs_up_before_writing():
    workflow = (ROOT / ".github" / "workflows" / "create-liu-practice.yml").read_text(
        encoding="utf-8"
    )

    assert "--create-missing" in workflow
    assert "dry_run:" in workflow
    assert "--apply --backup" in workflow
