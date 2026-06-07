# Prod Branch Auto Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split development and production branches, then deploy automatically only when `prod` changes.

**Architecture:** Keep `main` as the stable integration branch, create `dev` for daily development, and create `prod` from `main` for production releases. GitHub Actions listens to pushes on `prod`, logs into the Windows server through SSH, runs `deploy\deploy.ps1 -Branch prod`, and verifies the local HTTP service.

**Tech Stack:** Git branches, GitHub Actions, OpenSSH, PowerShell, existing `deploy\deploy.ps1`, Windows service `lxclgl`.

---

### File Structure

- Create: `.github/workflows/deploy-prod.yml`
  - GitHub Actions workflow that deploys only on `prod` branch pushes.
- Use existing: `deploy/deploy.ps1`
  - Server-side deployment script; already supports `-Branch`.
- Use existing: `deploy/install-service.ps1`
  - One-time server service installer; not normally called by CI.
- Use existing: `deploy/start-app.ps1`
  - Startup helper if NSSM is unavailable.
- Create local-only: `.ssh/lxclgl_github_actions`
  - Temporary private key generated locally for GitHub Actions secret upload, then removed after GitHub Secrets are configured.

### Task 1: Create Branches

**Files:**
- No file edits.

- [ ] **Step 1: Confirm current clean base**

Run:

```powershell
git fetch origin
git status --short
git branch --show-current
git log -1 --oneline
```

Expected:
- Current branch is `main`.
- Any unrelated local files are left untouched.
- `main` is at the latest intended baseline.

- [ ] **Step 2: Create local branches from main**

Run:

```powershell
git switch main
git branch dev main
git branch prod main
```

Expected:
- Local `dev` and `prod` branches exist.
- No deployment is triggered yet because branches have not been pushed.

- [ ] **Step 3: Push branches after user confirmation**

Run only after user confirms:

```powershell
git push origin dev
git push origin prod
```

Expected:
- Remote `origin/dev` and `origin/prod` exist.

### Task 2: Add Prod Deployment Workflow

**Files:**
- Create: `.github/workflows/deploy-prod.yml`

- [ ] **Step 1: Create workflow file**

Create `.github/workflows/deploy-prod.yml` with:

```yaml
name: Deploy prod

on:
  push:
    branches:
      - prod
  workflow_dispatch:

concurrency:
  group: lxclgl-prod-deploy
  cancel-in-progress: false

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy on Windows server
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.PROD_SSH_HOST }}
          username: ${{ secrets.PROD_SSH_USER }}
          key: ${{ secrets.PROD_SSH_KEY }}
          port: ${{ secrets.PROD_SSH_PORT || 22 }}
          script: |
            powershell -NoProfile -ExecutionPolicy Bypass -Command "
              $ErrorActionPreference = 'Stop'
              [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
              $AppDir = 'C:\wwwroot\lxclgl'
              Set-Location -LiteralPath $AppDir
              git fetch origin prod
              git checkout prod
              git pull --ff-only origin prod
              powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $AppDir 'deploy\deploy.ps1') -AppDir $AppDir -ServiceName 'lxclgl' -Branch 'prod' -Port 5000
              $response = Invoke-WebRequest -Uri 'http://127.0.0.1:5000' -UseBasicParsing -TimeoutSec 10
              if ([int]$response.StatusCode -ne 200) { throw 'HTTP health check failed' }
            "
```

- [ ] **Step 2: Validate YAML intent**

Run:

```powershell
Select-String -Path .github\workflows\deploy-prod.yml -Pattern "branches:|prod|deploy.ps1|PROD_SSH_KEY"
```

Expected:
- Workflow listens to `prod`.
- Workflow runs `deploy\deploy.ps1`.
- Workflow uses SSH key secret.

### Task 3: Configure SSH Key

**Files:**
- Create local temporary key: `.ssh/lxclgl_github_actions`
- Modify server: `C:\Users\Administrator\.ssh\authorized_keys`
- Configure GitHub Secrets:
  - `PROD_SSH_HOST=1.14.121.214`
  - `PROD_SSH_USER=Administrator`
  - `PROD_SSH_PORT=22`
  - `PROD_SSH_KEY=<private key content>`

- [ ] **Step 1: Generate deploy key locally**

Run:

```powershell
New-Item -ItemType Directory -Force -Path .ssh | Out-Null
ssh-keygen -t ed25519 -f .ssh\lxclgl_github_actions -N "" -C "github-actions-lxclgl-prod"
```

Expected:
- `.ssh\lxclgl_github_actions` and `.ssh\lxclgl_github_actions.pub` exist.

- [ ] **Step 2: Install public key on server**

Use SSH password once to append the `.pub` content to:

```text
C:\Users\Administrator\.ssh\authorized_keys
```

Expected:
- `ssh -i .ssh\lxclgl_github_actions Administrator@1.14.121.214 "echo ok"` succeeds.

- [ ] **Step 3: Configure GitHub Secrets**

Preferred command after `gh auth login`:

```powershell
gh secret set PROD_SSH_HOST --body "1.14.121.214"
gh secret set PROD_SSH_USER --body "Administrator"
gh secret set PROD_SSH_PORT --body "22"
gh secret set PROD_SSH_KEY < .ssh\lxclgl_github_actions
```

Expected:
- GitHub repository has all four secrets.

- [ ] **Step 4: Remove local private key after secret upload**

Run:

```powershell
Remove-Item -LiteralPath .ssh\lxclgl_github_actions -Force
```

Expected:
- Private key is no longer stored in the project directory.
- Public key can remain for reference or be removed too.

### Task 4: Commit and Push Workflow

**Files:**
- Commit: `.github/workflows/deploy-prod.yml`
- Do not commit: `.ssh/*`
- Do not commit unrelated local files.

- [ ] **Step 1: Stage only workflow file**

Run:

```powershell
git add .github\workflows\deploy-prod.yml
git status --short
```

Expected:
- Only `.github/workflows/deploy-prod.yml` is staged.
- Existing unrelated local files remain unstaged.

- [ ] **Step 2: Commit only after user confirmation**

Run only after user confirms:

```powershell
git commit -m "ci: deploy prod branch"
```

Expected:
- Commit contains only the workflow file.

- [ ] **Step 3: Push workflow to main/dev/prod intentionally**

Run only after user confirms the exact branch push plan:

```powershell
git push origin main
git switch dev
git merge --ff-only main
git push origin dev
git switch prod
git merge --ff-only main
git push origin prod
git switch main
```

Expected:
- Workflow exists on `prod`.
- The push to `prod` may trigger deployment once secrets exist.

### Task 5: First Prod Deployment Verification

**Files:**
- No file edits.

- [ ] **Step 1: Ask user before triggering prod deployment**

Ask:

```text
现在是否允许触发第一次 prod 自动部署？
```

- [ ] **Step 2: Trigger deployment only after confirmation**

Options:

```powershell
git switch prod
git commit --allow-empty -m "ci: trigger prod deploy"
git push origin prod
git switch main
```

or run GitHub Actions manually from the GitHub UI using `workflow_dispatch`.

- [ ] **Step 3: Verify server**

Run:

```powershell
curl.exe -I --max-time 15 http://1.14.121.214:5000
```

Expected:
- Response includes `HTTP/1.1 200 OK`.

### Self-Review

- Spec coverage: covers `main`, `dev`, `prod`, and automatic deployment on `prod` changes.
- Placeholder scan: no TBD/TODO placeholders.
- Risk controls: no commit, push, secrets change, or deployment trigger happens without user confirmation.
