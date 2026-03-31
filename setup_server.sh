#!/bin/bash

set -euo pipefail

APP_USER="${APP_USER:-yula}"
APP_GROUP="${APP_GROUP:-$APP_USER}"
APP_DIR="${APP_DIR:-/opt/yula-bot}"
ENV_FILE="${ENV_FILE:-/etc/yula-bot.env}"
SERVICE_NAME="${SERVICE_NAME:-yula-bot}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
    echo "This script must be run as root."
    exit 1
fi

echo "==> Installing system packages"
apt-get update
apt-get install -y python3 python3-pip python3-venv rsync

echo "==> Creating service account"
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
    useradd --system --create-home --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
fi

if ! getent group "${APP_GROUP}" >/dev/null 2>&1; then
    groupadd --system "${APP_GROUP}"
fi

usermod -g "${APP_GROUP}" "${APP_USER}"

echo "==> Syncing application files into ${APP_DIR}"
install -d -o "${APP_USER}" -g "${APP_GROUP}" -m 0750 "${APP_DIR}"
rsync -a --delete \
    --exclude '.env' \
    --exclude '__pycache__/' \
    --exclude 'venv/' \
    "${SOURCE_DIR}/" "${APP_DIR}/"
chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"

echo "==> Creating virtual environment"
python3 -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/pip" install --upgrade pip
"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

if [[ -f "${SOURCE_DIR}/.env" ]]; then
    echo "==> Installing environment file to ${ENV_FILE}"
    install -o root -g root -m 0600 "${SOURCE_DIR}/.env" "${ENV_FILE}"
elif [[ ! -f "${ENV_FILE}" ]]; then
    echo "No .env file found in ${SOURCE_DIR} and ${ENV_FILE} does not exist."
    echo "Create ${ENV_FILE} before starting the service."
    exit 1
fi

if ! grep -q '^LIVE_TRADING=' "${ENV_FILE}"; then
    echo "LIVE_TRADING=false" >> "${ENV_FILE}"
fi

echo "==> Installing systemd service"
install -o root -g root -m 0644 "${APP_DIR}/yula-bot.service" "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo "==> Service status"
systemctl --no-pager --full status "${SERVICE_NAME}" || true
echo "==> Recent logs"
journalctl -u "${SERVICE_NAME}" -n 50 --no-pager || true
