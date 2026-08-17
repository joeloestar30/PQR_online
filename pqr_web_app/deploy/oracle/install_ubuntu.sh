#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/joeloestar30/PQR_online.git}"
APP_ROOT="/opt/pqr/PQR_online"
APP_DIR="$APP_ROOT/pqr_web_app"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script with sudo."
  exit 1
fi

apt-get update
apt-get install -y git nginx python3 python3-venv python3-pip

if ! id pqr >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin pqr
fi

mkdir -p /opt/pqr /etc/pqr

if [[ -d "$APP_ROOT/.git" ]]; then
  git -C "$APP_ROOT" pull --ff-only
else
  git clone "$REPO_URL" "$APP_ROOT"
fi

chown -R pqr:pqr /opt/pqr

if [[ ! -d "$APP_DIR/.venv" ]]; then
  sudo -u pqr python3 -m venv "$APP_DIR/.venv"
fi

sudo -u pqr "$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
sudo -u pqr "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [[ ! -f /etc/pqr/pqr.env ]]; then
  cp "$APP_DIR/deploy/oracle/pqr.env.example" /etc/pqr/pqr.env
  chmod 600 /etc/pqr/pqr.env
  chown root:root /etc/pqr/pqr.env
  echo "Created /etc/pqr/pqr.env. Edit it with real secrets before starting services."
fi

cp "$APP_DIR/deploy/oracle/pqr-web.service" /etc/systemd/system/pqr-web.service
cp "$APP_DIR/deploy/oracle/pqr-worker.service" /etc/systemd/system/pqr-worker.service
cp "$APP_DIR/deploy/oracle/pqr-online.nginx" /etc/nginx/sites-available/pqr-online
ln -sf /etc/nginx/sites-available/pqr-online /etc/nginx/sites-enabled/pqr-online
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl daemon-reload
systemctl enable pqr-web pqr-worker nginx
systemctl restart nginx

echo "Install complete."
echo "Next:"
echo "  1. sudo nano /etc/pqr/pqr.env"
echo "  2. sudo systemctl restart pqr-web pqr-worker"
echo "  3. sudo systemctl status pqr-web pqr-worker --no-pager"

