from pathlib import Path


def test_deploy_script_checks_native_command_failures():
    script = Path('deploy/deploy.ps1').read_text(encoding='utf-8')

    assert 'Invoke-NativeCommandWithRetry' in script
    assert 'git fetch origin $Branch' in script
    assert '"git fetch origin $Branch failed"' in script
    assert 'git checkout $Branch' in script
    assert '"git checkout $Branch failed"' in script
    assert 'git pull --ff-only origin $Branch' in script
    assert '"git pull origin $Branch failed"' in script
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
    assert "Invoke-Retry 'pull'" in workflow
    assert 'petty-cash/usages/1' in workflow
    assert 'Installing Python dependencies' in deploy_script
    assert 'Start-Service -Name $ServiceName' in deploy_script
