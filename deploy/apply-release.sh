#!/usr/bin/env bash
set -euo pipefail

ARCHIVE_PATH="${1:?archive path required}"
COMMIT_SHA="${2:-manual}"

APP_BASE="${APP_BASE:-/opt/kol-monitor-trade}"
STATE_DIR="${STATE_DIR:-/var/lib/kol-monitor-trade}"
ENV_DIR="${ENV_DIR:-/etc/kol-monitor-trade}"
SERVICE_NAME="${SERVICE_NAME:-kol-monitor-trade}"
PORT="${PORT:-8000}"
PYPI_INDEX="${PYPI_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
INSTALL_SELFCORD="${INSTALL_SELFCORD:-false}"
RELEASE_ID="$(date -u +%Y%m%d%H%M%S)-${COMMIT_SHA:0:12}"
RELEASE_DIR="$APP_BASE/releases/$RELEASE_ID"
VENV_DIR="$APP_BASE/venv"

mkdir -p "$APP_BASE/releases" "$STATE_DIR/data" "$ENV_DIR" "$RELEASE_DIR"
tar -xzf "$ARCHIVE_PATH" -C "$RELEASE_DIR"

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --timeout 120 -i "$PYPI_INDEX" --upgrade pip

if [[ -f "$RELEASE_DIR/requirements.txt" ]]; then
  grep -v '^selfcord.py @' "$RELEASE_DIR/requirements.txt" > /tmp/kol-requirements.txt
  "$VENV_DIR/bin/pip" install --timeout 120 -i "$PYPI_INDEX" -r /tmp/kol-requirements.txt
  if [[ "$INSTALL_SELFCORD" == "true" ]]; then
    "$VENV_DIR/bin/pip" install --timeout 60 \
      'selfcord.py @ https://github.com/dolfies/discord.py-self/archive/69819fc8bca2b81849cbfec45c00e2c2d0811231.zip'
  fi
fi

if [[ ! -f "$ENV_DIR/app.env" ]]; then
  echo "Missing $ENV_DIR/app.env" >&2
  exit 1
fi

ln -sfn "$RELEASE_DIR" "$APP_BASE/current"
id -u koltrade >/dev/null 2>&1 || useradd --system --home "$STATE_DIR" --shell /usr/sbin/nologin koltrade
chown -R koltrade:koltrade "$APP_BASE" "$STATE_DIR"
chown root:koltrade "$ENV_DIR/app.env"
chmod 640 "$ENV_DIR/app.env"
chmod 700 "$STATE_DIR/data"

cat > /etc/systemd/system/"$SERVICE_NAME".service <<UNIT
[Unit]
Description=KOL Monitor Trade
After=network-online.target mysql.service
Wants=network-online.target

[Service]
Type=simple
User=koltrade
Group=koltrade
WorkingDirectory=$APP_BASE/current
EnvironmentFile=$ENV_DIR/app.env
Environment="HTTP_PROXY=" "HTTPS_PROXY=" "ALL_PROXY=" "http_proxy=" "https_proxy=" "all_proxy="
Environment="NO_PROXY=127.0.0.1,localhost,::1" "no_proxy=127.0.0.1,localhost,::1"
ExecStart=$VENV_DIR/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port $PORT --log-level info
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/nginx/sites-available/kol-monitor-trade <<'NGINX'
server {
    listen 80 default_server;
    listen 8888;
    server_name _;

    location /market/api/ {
        proxy_pass http://127.0.0.1:18082/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /market/ {
        root /var/www/market-opinion-tracker;
        try_files $uri $uri/ /market/index.html;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINX

rm -f /etc/nginx/sites-enabled/default
ln -sfn /etc/nginx/sites-available/kol-monitor-trade /etc/nginx/sites-enabled/kol-monitor-trade
nginx -t
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
systemctl reload nginx

for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null; then
    find "$APP_BASE/releases" -mindepth 1 -maxdepth 1 -type d | sort -r | tail -n +6 | xargs -r rm -rf
    rm -f "$ARCHIVE_PATH"
    echo "deployed $COMMIT_SHA"
    exit 0
  fi
  sleep 2
done

journalctl -u "$SERVICE_NAME" -n 80 --no-pager >&2 || true
exit 1
