#!/usr/bin/env bash
set -euo pipefail

MIHOMO_HOME="${MIHOMO_HOME:-/etc/mihomo}"
MIHOMO_STATE="${MIHOMO_STATE:-/var/lib/mihomo}"
MIHOMO_PORT="${MIHOMO_PORT:-7897}"
MIHOMO_CONTROLLER="${MIHOMO_CONTROLLER:-127.0.0.1:9090}"
MIHOMO_VERSION="${MIHOMO_VERSION:-}"
MIHOMO_CONFIG_URL="${MIHOMO_CONFIG_URL:-}"
APP_ENV="${APP_ENV:-/etc/kol-monitor-trade/app.env}"
UPDATE_APP_ENV="${UPDATE_APP_ENV:-true}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Please run as root." >&2
  exit 1
fi

apt-get update
apt-get install -y ca-certificates curl gzip git python3

if [[ -z "$MIHOMO_VERSION" ]]; then
  MIHOMO_VERSION="$(git ls-remote --tags --refs https://github.com/MetaCubeX/mihomo.git \
    | awk -F/ '/refs\/tags\/v[0-9]+\.[0-9]+\.[0-9]+$/ {print $NF}' \
    | sort -V | tail -n 1)"
fi

case "$(uname -m)" in
  x86_64|amd64) asset="mihomo-linux-amd64-compatible-${MIHOMO_VERSION}.gz" ;;
  aarch64|arm64) asset="mihomo-linux-arm64-${MIHOMO_VERSION}.gz" ;;
  *) echo "Unsupported architecture: $(uname -m)" >&2; exit 1 ;;
esac

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
download_url="https://github.com/MetaCubeX/mihomo/releases/download/${MIHOMO_VERSION}/${asset}"
curl -fL "$download_url" -o "$tmp_dir/mihomo.gz"
gzip -dc "$tmp_dir/mihomo.gz" > /usr/local/bin/mihomo
chmod 755 /usr/local/bin/mihomo

id -u mihomo >/dev/null 2>&1 || useradd --system --home "$MIHOMO_STATE" --shell /usr/sbin/nologin mihomo
mkdir -p "$MIHOMO_HOME" "$MIHOMO_STATE"
chown -R mihomo:mihomo "$MIHOMO_STATE"
chmod 750 "$MIHOMO_STATE"

if [[ -n "$MIHOMO_CONFIG_URL" ]]; then
  curl -fL "$MIHOMO_CONFIG_URL" -o "$MIHOMO_HOME/config.yaml"
elif [[ ! -f "$MIHOMO_HOME/config.yaml" ]]; then
  echo "Missing mihomo config. Set MIHOMO_CONFIG_URL or create $MIHOMO_HOME/config.yaml." >&2
  exit 1
fi

python3 - "$MIHOMO_HOME/config.yaml" "$MIHOMO_PORT" "$MIHOMO_CONTROLLER" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
managed = {
    "mixed-port": sys.argv[2],
    "allow-lan": "false",
    "bind-address": "127.0.0.1",
    "external-controller": sys.argv[3],
}
lines = path.read_text(encoding="utf-8").splitlines()
seen = set()
out = []
for line in lines:
    match = re.match(r"^([A-Za-z0-9_-]+)\s*:", line)
    key = match.group(1) if match else ""
    if key in managed:
        if key not in seen:
            out.append(f"{key}: {managed[key]}")
            seen.add(key)
        continue
    out.append(line)
prefix = [f"{key}: {value}" for key, value in managed.items() if key not in seen]
path.write_text("\n".join(prefix + out).rstrip() + "\n", encoding="utf-8")
PY

chown root:mihomo "$MIHOMO_HOME/config.yaml"
chmod 640 "$MIHOMO_HOME/config.yaml"

/usr/local/bin/mihomo -t -d "$MIHOMO_STATE" -f "$MIHOMO_HOME/config.yaml"

cat > /etc/systemd/system/mihomo.service <<UNIT
[Unit]
Description=Mihomo proxy service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=mihomo
Group=mihomo
WorkingDirectory=$MIHOMO_STATE
ExecStart=/usr/local/bin/mihomo -d $MIHOMO_STATE -f $MIHOMO_HOME/config.yaml
Restart=always
RestartSec=5
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now mihomo
sleep 2
systemctl --no-pager --full status mihomo

curl -fsS --proxy "http://127.0.0.1:${MIHOMO_PORT}" \
  "https://api.bitget.com/api/v2/public/time" >/dev/null

if [[ "$UPDATE_APP_ENV" == "true" && -f "$APP_ENV" ]]; then
  cp "$APP_ENV" "${APP_ENV}.bak.$(date -u +%Y%m%d%H%M%S)"
  python3 - "$APP_ENV" "$MIHOMO_PORT" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
port = sys.argv[2]
updates = {
    "TRADING_PROXY_URL": f"http://127.0.0.1:{port}",
    "TELEGRAM_PROXY_URL": f"socks5://127.0.0.1:{port}",
}
lines = path.read_text(encoding="utf-8").splitlines()
seen = set()
out = []
for line in lines:
    key = line.split("=", 1)[0] if "=" in line else ""
    if key in updates:
        out.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        out.append(line)
for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")
path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
PY
  systemctl restart kol-monitor-trade || true
fi

echo "mihomo ${MIHOMO_VERSION} is ready on 127.0.0.1:${MIHOMO_PORT}"
