#!/bin/bash
# Stargazer Downloader - Auto Deploy Script
# Jalankan di VPS: bash deploy.sh

set -e

echo "=== Stargazer Downloader - Deploy ==="

# 1. Install system dependencies
echo "[1/6] Installing system dependencies..."
sudo apt update
sudo apt install -y python3 python3-pip python3-venv ffmpeg git

# 2. Clone repo
echo "[2/6] Cloning repository..."
cd ~
if [ -d "Stargazer-Downloader" ]; then
    echo "Directory exists, pulling latest..."
    cd Stargazer-Downloader
    git pull
else
    git clone https://github.com/mrfunntastiic/Stargazer-Downloader.git
    cd Stargazer-Downloader
fi

# 3. Setup Python venv
echo "[3/6] Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Create .env if not exists
echo "[4/6] Configuring .env..."
if [ ! -f .env ]; then
    cp .env.example .env
    CURRENT_IP=$(curl -s ifconfig.me 2>/dev/null || echo "43.156.7.213")
    sed -i "s|http://localhost:8000|http://${CURRENT_IP}:8000|g" .env
    echo ""
    echo "================================================"
    echo "PENTING: Edit file .env dan isi TELEGRAM_BOT_TOKEN"
    echo "  nano ~/Stargazer-Downloader/.env"
    echo "================================================"
    echo ""
fi

# 5. Create systemd services
echo "[5/6] Creating systemd services..."
WORK_DIR=$(pwd)
VENV_PATH="${WORK_DIR}/venv/bin"
CURRENT_USER=$(whoami)

sudo tee /etc/systemd/system/stargazer-web.service > /dev/null <<EOF
[Unit]
Description=Stargazer Web API
After=network.target

[Service]
User=${CURRENT_USER}
WorkingDirectory=${WORK_DIR}
Environment="PATH=${VENV_PATH}"
ExecStart=${VENV_PATH}/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/stargazer-bot.service > /dev/null <<EOF
[Unit]
Description=Stargazer Telegram Bot
After=network.target stargazer-web.service

[Service]
User=${CURRENT_USER}
WorkingDirectory=${WORK_DIR}
Environment="PATH=${VENV_PATH}"
ExecStart=${VENV_PATH}/python bot.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# 6. Start services
echo "[6/6] Starting services..."
sudo systemctl daemon-reload
sudo systemctl enable stargazer-web stargazer-bot
sudo systemctl start stargazer-web stargazer-bot

CURRENT_IP=$(curl -s ifconfig.me 2>/dev/null || echo "43.156.7.213")

echo ""
echo "============================================"
echo "  DEPLOY SELESAI!"
echo "============================================"
echo "  Web UI:  http://${CURRENT_IP}:8000"
echo "  Status:  sudo systemctl status stargazer-web"
echo "           sudo systemctl status stargazer-bot"
echo "  Logs:    sudo journalctl -u stargazer-web -f"
echo "           sudo journalctl -u stargazer-bot -f"
echo ""
echo "  JANGAN LUPA: Edit .env isi TELEGRAM_BOT_TOKEN"
echo "    nano ~/Stargazer-Downloader/.env"
echo "    sudo systemctl restart stargazer-bot"
echo "============================================"