#!/bin/bash

set -euo pipefail

SERVER_IP="${SERVER_IP:-46.62.223.244}"
SERVER_USER="${SERVER_USER:-root}"
UPLOAD_DIR="${UPLOAD_DIR:-/root/yula-bootstrap}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

FILES=(
    ".env.example"
    "bot_runner.py"
    "binance_ws.py"
    "config.py"
    "data_manager.py"
    "trader.py"
    "yula_strategy.py"
    "requirements.txt"
    "yula-bot.service"
    "setup_server.sh"
)

TEMP_DIR="${SOURCE_DIR}/deployment_temp"
rm -rf "${TEMP_DIR}"
mkdir -p "${TEMP_DIR}"

echo "==> Building deployment package"
for file in "${FILES[@]}"; do
    cp "${SOURCE_DIR}/${file}" "${TEMP_DIR}/"
done

if [[ -f "${SOURCE_DIR}/.env" ]]; then
    cp "${SOURCE_DIR}/.env" "${TEMP_DIR}/.env"
fi

echo "==> Uploading package to ${SERVER_USER}@${SERVER_IP}:${UPLOAD_DIR}"
ssh "${SERVER_USER}@${SERVER_IP}" "rm -rf '${UPLOAD_DIR}' && mkdir -p '${UPLOAD_DIR}'"
scp -r "${TEMP_DIR}/." "${SERVER_USER}@${SERVER_IP}:${UPLOAD_DIR}/"

rm -rf "${TEMP_DIR}"

echo
echo "Upload completed."
echo "Next steps:"
echo "  1. SSH to the server: ssh ${SERVER_USER}@${SERVER_IP}"
echo "  2. Run: cd ${UPLOAD_DIR} && chmod +x setup_server.sh && ./setup_server.sh"
