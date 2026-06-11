from pathlib import Path


def test_deploy_script_checks_native_command_failures():
    script = Path('deploy/deploy.ps1').read_text(encoding='utf-8')

    assert 'git fetch origin $Branch' in script
    assert 'throw "git fetch origin $Branch failed"' in script
    assert 'git checkout $Branch' in script
    assert 'throw "git checkout $Branch failed"' in script
    assert 'git pull --ff-only origin $Branch' in script
    assert 'throw "git pull origin $Branch failed"' in script
    assert 'throw "pip install failed"' in script


def test_deploy_script_restarts_service_with_port_cleanup_fallback():
    script = Path('deploy/deploy.ps1').read_text(encoding='utf-8')

    assert 'Stop-Service -Name $ServiceName' in script
    assert 'Get-NetTCPConnection -LocalPort $Port -State Listen' in script
    assert 'Stop-Process -Id $Process.Id -Force' in script
    assert 'Start-Service -Name $ServiceName' in script
    assert 'throw "Windows service $ServiceName failed to start"' in script
