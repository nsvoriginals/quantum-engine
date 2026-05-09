#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# AuditSmart Quantum — one-shot EC2 setup (Ubuntu 22.04 / 24.04)
#
# Usage (run once on your EC2 instance):
#   git clone <your-repo> quantum-engine
#   cd quantum-engine
#   sudo ./deploy/setup-ec2.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}   $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}     $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}   $*"; }
die()     { echo -e "${RED}[ERROR]${NC}  $*"; exit 1; }

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
APP_USER="${SUDO_USER:-ubuntu}"
VENV="$APP_DIR/.venv"
SERVICE_NAME="quantum-engine"

# ── Must run as root ─────────────────────────────────────────────────────────
[[ "$EUID" -ne 0 ]] && die "Run with sudo:  sudo ./deploy/setup-ec2.sh"

echo ""
echo "  ╔════════════════════════════════════════╗"
echo "  ║   AuditSmart Quantum — EC2 Setup       ║"
echo "  ╚════════════════════════════════════════╝"
echo ""

# ── Prompts ──────────────────────────────────────────────────────────────────
read -rp "  EC2 public IP or domain (e.g. 1.2.3.4 or api.yoursite.com): " APP_HOST
read -rp "  Frontend URL for CORS (e.g. https://yoursite.com):           " FRONTEND_URL

if [[ "$APP_HOST" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    SETUP_SSL="n"
    warn "IP detected — skipping HTTPS (SSL needs a domain name, not an IP)"
else
    read -rp "  Set up free HTTPS with Let's Encrypt? [y/n]:                " SETUP_SSL
fi
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# 1. SWAP  (quantum libs need ~800 MB — t2.micro only has 1 GB RAM)
# ─────────────────────────────────────────────────────────────────────────────
info "Checking swap..."
if swapon --show | grep -q /swapfile 2>/dev/null; then
    ok "Swap already present — skipping"
else
    info "Adding 2 GB swap file..."
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap  /swapfile
    swapon  /swapfile
    grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    ok "Swap added"
fi

# ─────────────────────────────────────────────────────────────────────────────
# 2. SYSTEM PACKAGES
# ─────────────────────────────────────────────────────────────────────────────
info "Installing system packages (Python 3.11, Nginx, Certbot, git)..."
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3.11 python3.11-venv python3-pip \
    nginx certbot python3-certbot-nginx \
    git curl build-essential > /dev/null
ok "Packages installed"

# ─────────────────────────────────────────────────────────────────────────────
# 3. PYTHON VIRTUAL ENV + DEPENDENCIES
# ─────────────────────────────────────────────────────────────────────────────
info "Setting up Python virtual environment..."
if [[ ! -d "$VENV" ]]; then
    python3.11 -m venv "$VENV"
fi

info "Installing Python dependencies (this takes 3–5 minutes the first time)..."
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
ok "Python env ready at $VENV"

# ─────────────────────────────────────────────────────────────────────────────
# 4. .env FILE
# ─────────────────────────────────────────────────────────────────────────────
info "Configuring .env..."
ENV_FILE="$APP_DIR/.env"
[[ ! -f "$ENV_FILE" ]] && cp "$APP_DIR/.env.example" "$ENV_FILE"

# Only write t2.micro-safe defaults; never overwrite existing custom values
sed -i "s|^ALLOWED_ORIGINS=.*|ALLOWED_ORIGINS=${FRONTEND_URL}|"  "$ENV_FILE"
sed -i "s|^WORKERS=.*|WORKERS=1|"                                 "$ENV_FILE"
sed -i "s|^LOG_FORMAT=.*|LOG_FORMAT=text|"                        "$ENV_FILE"

ok ".env configured at $ENV_FILE"

# ─────────────────────────────────────────────────────────────────────────────
# 5. SYSTEMD SERVICE
# ─────────────────────────────────────────────────────────────────────────────
info "Installing systemd service..."
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=AuditSmart Quantum API
After=network.target

[Service]
User=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment="PATH=${VENV}/bin"
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV}/bin/gunicorn api.endpoints:app -c gunicorn.conf.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable  "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
ok "Service '${SERVICE_NAME}' started"

# ─────────────────────────────────────────────────────────────────────────────
# 6. NGINX REVERSE PROXY
# ─────────────────────────────────────────────────────────────────────────────
info "Configuring Nginx..."
cat > /etc/nginx/sites-available/${SERVICE_NAME} << EOF
server {
    listen 80;
    server_name ${APP_HOST};

    location / {
        proxy_pass         http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 180s;
        proxy_send_timeout 180s;
    }
}
EOF

rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/${SERVICE_NAME} /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
ok "Nginx configured"

# ─────────────────────────────────────────────────────────────────────────────
# 7. HTTPS / SSL (domain only)
# ─────────────────────────────────────────────────────────────────────────────
if [[ "${SETUP_SSL,,}" == "y" ]]; then
    info "Setting up SSL with Let's Encrypt..."
    CERTBOT_EMAIL="admin@${APP_HOST#*.}"
    certbot --nginx -d "$APP_HOST" --non-interactive --agree-tos -m "$CERTBOT_EMAIL"
    ok "SSL certificate installed"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Done
# ─────────────────────────────────────────────────────────────────────────────
PROTO="http"; [[ "${SETUP_SSL,,}" == "y" ]] && PROTO="https"

echo ""
echo -e "  ${GREEN}Setup complete!${NC}"
echo ""
echo "  API is live at:    ${PROTO}://${APP_HOST}"
echo "  Health check:      ${PROTO}://${APP_HOST}/health"
echo "  API docs (Swagger):${PROTO}://${APP_HOST}/docs"
echo ""
echo "  Day-to-day commands (run from the repo directory):"
echo "    sudo systemctl status  ${SERVICE_NAME}   # is it running?"
echo "    sudo journalctl -fu    ${SERVICE_NAME}   # live logs"
echo "    sudo systemctl restart ${SERVICE_NAME}   # restart"
echo "    make update                               # git pull + restart"
echo ""
