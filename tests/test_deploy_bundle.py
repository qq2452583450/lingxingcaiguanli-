import base64
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
def bundle_repositories(tmp_path):
    source = tmp_path / 'source'
    server = tmp_path / 'server'
    source.mkdir()
    git(source, 'init', '-b', 'prod')
    (source / 'app.txt').write_text('old', encoding='utf-8')
    git(source, 'add', 'app.txt')
    git(source, 'commit', '-m', 'initial')
    git(tmp_path, 'clone', str(source), str(server))
    git(server, 'remote', 'set-url', 'origin', 'https://github.invalid/not-accessible.git')
    (source / 'app.txt').write_text('new', encoding='utf-8')
    git(source, 'commit', '-am', 'release')
    bundle = server / 'deploy-production.bundle'
    git(source, 'bundle', 'create', str(bundle), 'HEAD')
    return source, server, bundle


def test_bundle_updates_revision_without_accessing_remote(bundle_repositories):
    source, server, bundle = bundle_repositories
    (server / 'runtime-data.txt').write_text('keep me', encoding='utf-8')
    git(server, 'bundle', 'verify', str(bundle))
    git(server, 'fetch', '--no-tags', str(bundle), 'HEAD:refs/remotes/origin/prod')
    git(server, 'rebase', 'origin/prod')
    assert git(server, 'rev-parse', 'HEAD') == git(source, 'rev-parse', 'HEAD')
    assert (server / 'app.txt').read_text(encoding='utf-8') == 'new'
    assert (server / 'runtime-data.txt').read_text(encoding='utf-8') == 'keep me'


def test_windows_workflow_syncs_bundle_with_native_git_stderr(bundle_repositories):
    powershell = shutil.which('powershell.exe')
    if not powershell:
        pytest.skip('Windows PowerShell integration test')
    yaml = pytest.importorskip('yaml')
    source, server, bundle = bundle_repositories
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
    assert not bundle.exists()


def test_windows_bundle_upload_preserves_binary_bytes(bundle_repositories):
    powershell = shutil.which('powershell.exe')
    if not powershell:
        pytest.skip('Windows PowerShell integration test')
    yaml = pytest.importorskip('yaml')
    source, server, bundle = bundle_repositories
    workflow = yaml.safe_load(Path('.github/workflows/deploy-prod.yml').read_text(encoding='utf-8'))
    step = next(step for step in workflow['jobs']['deploy']['steps'] if step['name'] == 'Transfer verified Git bundle')
    target = server / 'uploaded.bundle'
    script = step['env']['BUNDLE_UPLOAD_SCRIPT'].replace(
        'C:\\wwwroot\\lxclgl\\deploy-production.bundle', str(target)
    )
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    result = subprocess.run(
        [powershell, '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
        input=bundle.read_bytes(), capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert target.read_bytes() == bundle.read_bytes()
    git(server, 'bundle', 'verify', str(target))


def test_bundle_transfer_shell_has_valid_bash_syntax():
    bash = shutil.which('bash')
    if not bash:
        pytest.skip('Bash is unavailable')
    yaml = pytest.importorskip('yaml')
    workflow = yaml.safe_load(Path('.github/workflows/deploy-prod.yml').read_text(encoding='utf-8'))
    step = next(step for step in workflow['jobs']['deploy']['steps'] if step['name'] == 'Transfer verified Git bundle')
    result = subprocess.run([bash, '-n'], input=step['run'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('expected', ['', 'invalid-revision'])
def test_skip_sync_rejects_missing_or_wrong_revision_before_installing(expected, bundle_repositories, monkeypatch):
    powershell = shutil.which('powershell.exe')
    if not powershell:
        pytest.skip('Windows PowerShell integration test')
    source, server, bundle = bundle_repositories
    monkeypatch.setenv('SECRET_KEY', 'test-only-not-a-production-secret')
    result = subprocess.run(
        [powershell, '-NoProfile', '-NonInteractive', '-File', str(Path('deploy/deploy.ps1').resolve()),
         '-AppDir', str(server), '-SkipGitSync', '-ExpectedCommit', expected],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert 'Installing Python dependencies' not in result.stdout
    assert ('ExpectedCommit is required' in result.stderr
            or 'Production revision does not match expected commit' in result.stderr)
