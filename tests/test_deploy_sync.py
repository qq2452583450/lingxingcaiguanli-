import shutil
import subprocess
from pathlib import Path

import pytest


def git(directory, *args):
    return subprocess.run(
        ['git', '-c', 'user.name=Deploy Test', '-c', 'user.email=deploy-test@example.invalid', *args],
        cwd=directory, check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture
def deployment_repositories(tmp_path):
    source = tmp_path / 'source'
    server = tmp_path / 'server'
    source.mkdir()
    git(source, 'init', '-b', 'prod')
    (source / 'app.txt').write_text('old', encoding='utf-8')
    git(source, 'add', 'app.txt')
    git(source, 'commit', '-m', 'initial')
    git(tmp_path, 'clone', str(source), str(server))
    (source / 'app.txt').write_text('new', encoding='utf-8')
    git(source, 'commit', '-am', 'release')
    git(source, 'branch', 'deploy-release')
    sha = git(source, 'rev-parse', 'HEAD')
    git(source, 'bundle', 'create', str(server / f'deploy-production-{sha}.bundle'), 'refs/heads/deploy-release')
    # Server-side deployment must not need a reachable GitHub remote.
    git(server, 'remote', 'set-url', 'origin', 'https://unreachable.example.invalid/repository.git')
    return source, server


def test_windows_workflow_syncs_origin_with_native_git_stderr(deployment_repositories):
    powershell = shutil.which('powershell.exe')
    if not powershell:
        pytest.skip('Windows PowerShell integration test')
    yaml = pytest.importorskip('yaml')
    source, server = deployment_repositories
    (server / 'runtime-data.txt').write_text('keep me', encoding='utf-8')
    (server / 'app.txt').write_text('local edit', encoding='utf-8')
    workflow = yaml.safe_load(Path('.github/workflows/deploy-prod.yml').read_text(encoding='utf-8'))
    step = next(step for step in workflow['jobs']['deploy']['steps'] if step['name'] == 'Sync prod source')
    command = step['with']['script'].strip()
    script = command.split('-Command "', 1)[1].removesuffix('"')
    script = script.replace('C:\\wwwroot\\lxclgl', str(server))
    script = script.replace('${{ github.sha }}', git(source, 'rev-parse', 'HEAD'))
    result = subprocess.run(
        [powershell, '-NoProfile', '-NonInteractive', '-Command', script],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert git(server, 'rev-parse', 'HEAD') == git(source, 'rev-parse', 'HEAD')
    assert (server / 'app.txt').read_text(encoding='utf-8') == 'new'
    assert (server / 'runtime-data.txt').read_text(encoding='utf-8') == 'keep me'
    assert 'local edit' in git(server, 'stash', 'show', '-p')


def test_workflow_rejects_wrong_revision(deployment_repositories):
    powershell = shutil.which('powershell.exe')
    if not powershell:
        pytest.skip('Windows PowerShell integration test')
    source, server = deployment_repositories
    yaml = pytest.importorskip('yaml')
    workflow = yaml.safe_load(Path('.github/workflows/deploy-prod.yml').read_text(encoding='utf-8'))
    step = next(step for step in workflow['jobs']['deploy']['steps'] if step['name'] == 'Sync prod source')
    script = step['with']['script'].strip().split('-Command "', 1)[1].removesuffix('"')
    sha = git(source, 'rev-parse', 'HEAD')
    shutil.copy(server / f'deploy-production-{sha}.bundle', server / 'deploy-production-invalid-revision.bundle')
    script = script.replace('C:\\wwwroot\\lxclgl', str(server)).replace('${{ github.sha }}', 'invalid-revision')
    result = subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-Command', script], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'Production revision mismatch' in result.stderr


@pytest.mark.parametrize('expected', ['', 'invalid-revision'])
def test_skip_sync_rejects_missing_or_wrong_revision_before_installing(expected, deployment_repositories, monkeypatch):
    powershell = shutil.which('powershell.exe')
    if not powershell:
        pytest.skip('Windows PowerShell integration test')
    source, server = deployment_repositories
    monkeypatch.setenv('SECRET_KEY', 'test-only-not-a-production-secret')
    result = subprocess.run(
        [powershell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(Path('deploy/deploy.ps1').resolve()),
         '-AppDir', str(server), '-SkipGitSync', '-ExpectedCommit', expected],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert 'Installing Python dependencies' not in result.stdout
    assert ('ExpectedCommit is required' in result.stderr
            or 'Production revision does not match expected commit' in result.stderr)
