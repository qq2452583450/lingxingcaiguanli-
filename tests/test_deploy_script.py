from pathlib import Path


def test_deploy_script_checks_native_command_failures():
    script = Path('deploy/deploy.ps1').read_text(encoding='utf-8')

    assert 'Invoke-NativeCommandWithRetry' in script
    assert 'git fetch origin $Branch' in script
    assert '"git fetch origin $Branch failed"' in script
    assert 'git checkout $Branch' in script
    assert '"git checkout $Branch failed"' in script
    assert 'git rebase "origin/$Branch"' in script
    assert '"git rebase origin/$Branch failed"' in script
    assert 'throw "pip install failed"' in script


def test_deploy_script_restarts_service_with_port_cleanup_fallback():
    script = Path('deploy/deploy.ps1').read_text(encoding='utf-8')

    assert 'Stop-Service -Name $ServiceName' in script
    assert 'Get-NetTCPConnection -LocalPort $Port -State Listen' in script
    assert 'Clearing Python listener on port $TargetPort before service start.' in script
    assert 'Get-CimInstance Win32_Process' in script
    assert 'CommandLine -like "*$AppDir*"' in script
    assert 'Stop-Process -Id $Process.Id -Force' in script
    assert 'Start-Service -Name $ServiceName' in script
    assert 'throw "Windows service $ServiceName failed to start"' in script


def test_workflow_uses_deploy_script_for_dependency_install_before_restart():
    workflow = Path('.github/workflows/deploy-prod.yml').read_text(encoding='utf-8')
    deploy_script = Path('deploy/deploy.ps1').read_text(encoding='utf-8')

    assert 'deploy\\deploy.ps1' in workflow
    assert 'deploy\\force-restart-app.ps1' not in workflow
    assert "Invoke-Retry 'rebase'" in workflow
    assert 'petty-cash/usages/1' in workflow
    assert 'petty-cash/usages/1/reimburse' in workflow
    assert 'petty_cash_reimburse_allow' in workflow
    assert "'POST'" in workflow
    assert 'Installing Python dependencies' in deploy_script
    assert 'Start-Service -Name $ServiceName' in deploy_script


def test_production_workflow_transfers_bundle_and_does_not_fetch_github_on_server():
    workflow = Path('.github/workflows/deploy-prod.yml').read_text(encoding='utf-8')
    assert 'actions/checkout@v4' in workflow
    assert 'fetch-depth: 0' in workflow
    assert 'git bundle create production.bundle HEAD' in workflow
    assert 'timeout --foreground 120s scp' in workflow
    assert 'OpenStandardInput' not in workflow
    assert 'git fetch --no-tags $Bundle HEAD:refs/remotes/origin/prod' in workflow
    assert 'git bundle verify $Bundle' in workflow
    assert 'git fetch origin prod' not in workflow
    assert '-SkipGitSync -ExpectedCommit ${{ github.sha }}' in workflow
    assert 'StrictHostKeyChecking=yes' in workflow
    assert 'BatchMode=yes' in workflow


def test_deploy_skip_sync_requires_exact_expected_revision():
    script = Path('deploy/deploy.ps1').read_text(encoding='utf-8')
    assert '[switch]$SkipGitSync' in script
    assert '[string]$ExpectedCommit' in script
    assert 'if ($SkipGitSync)' in script
    assert 'ExpectedCommit is required when skipping Git sync' in script
    assert '$ActualCommit -ne $ExpectedCommit' in script
    assert 'Production revision does not match expected commit' in script


def test_production_deployment_rejects_non_prod_manual_runs():
    workflow = Path('.github/workflows/deploy-prod.yml').read_text(encoding='utf-8')
    assert "    if: github.ref == 'refs/heads/prod'" in workflow
