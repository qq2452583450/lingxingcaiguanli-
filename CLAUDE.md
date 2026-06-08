# Claude Code Project Rules

## Language

- Speak Chinese by default.
- Keep explanations practical and concise.

## Branch Workflow

- Default development branch is `dev`.
- `main` is the stable main branch.
- `prod` is the production branch.
- Pushing `prod` triggers automatic production deployment through GitHub Actions.
- Daily code changes must happen on `dev`.
- Do not work directly on `main` or `prod` unless the user explicitly asks.

## Git Safety

- Do not commit, push, merge, or deploy unless the user explicitly agrees in the current conversation.
- Before staging files, inspect `git status --short`.
- Stage only files related to the current task.
- If unrelated local changes exist, leave them untouched.
- If the user asks to save work to `dev`, commit and push only after showing the files that will be included.
- If the user asks to sync `dev`, run `git switch dev` and `git pull origin dev`.

## Deployment

- The server project path is `C:\wwwroot\lxclgl`.
- Production deploy is triggered by changes to `prod`.
- Do not connect to the server or run deployment scripts unless the user explicitly asks.
- Do not push `prod` unless the user explicitly confirms production release.

## Files Never To Commit

- Database files: `*.db`, `*.sqlite`, `*.sqlite3`
- Cookies: `cookies.txt`
- Secrets: `.env`, `.env.*`, `deploy/server.env.ps1`
- Logs: `*.log`, `.server-*.log`
- SSH keys, GitHub tokens, passwords, API keys
- Temporary Excel, Word, PDF, or scratch files unless the user explicitly asks
- Python cache folders: `__pycache__/`

## Engineering Preferences

- Preserve the existing Flask, SQLite, HTML, CSS, and JavaScript structure.
- Prefer small, focused fixes over broad refactors.
- Add or update tests for behavior changes when practical.
- Run relevant tests before claiming a fix is complete.
- For frontend changes, verify that text does not overlap and workflows remain usable.
