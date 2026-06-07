#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/www/lxclgl}"
SERVICE_NAME="${SERVICE_NAME:-lxclgl}"
BRANCH="${BRANCH:-main}"
DB_FILE="${DB_FILE:-零星材管理系统.db}"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"
VENV_DIR="${VENV_DIR:-$APP_DIR/.venv}"

cd "$APP_DIR"

mkdir -p "$BACKUP_DIR"

if [ -f "$DB_FILE" ]; then
  backup_path="$BACKUP_DIR/${DB_FILE}.bak-$(date +%Y%m%d-%H%M%S)"
  echo "Backing up database to $backup_path"
  cp "$DB_FILE" "$backup_path"
else
  echo "Database $DB_FILE not found, skipping backup"
fi

echo "Fetching latest code from origin/$BRANCH"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment at $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

echo "Installing Python dependencies"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install -r requirements.txt

echo "Restarting service: $SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo "Service status"
sudo systemctl status "$SERVICE_NAME" --no-pager
