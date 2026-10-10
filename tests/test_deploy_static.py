from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_prod_deploy_checks_actual_signature_html():
    workflow = (ROOT / '.github/workflows/deploy-prod.yml').read_text(encoding='utf-8')
    assert 'name: Verify production signature sheets' in workflow
    assert 'verify_inquiry_approval_print.py' in workflow
    script = (ROOT / 'tools/verify_inquiry_approval_print.py').read_text(encoding='utf-8')
    assert '?mode=ro' in script
    assert 'http://127.0.0.1:5000/api/purchase-inquiries/' in script
    assert "'<table' not in html" in script


def test_signature_formatter_avoids_python39_only_string_methods():
    import ast
    source = (ROOT / 'blueprints/inquiries.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    helper = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == 'historical_price')
    assert not any(isinstance(node, ast.Attribute) and node.attr in ('removeprefix', 'removesuffix')
                   for node in ast.walk(helper))


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
