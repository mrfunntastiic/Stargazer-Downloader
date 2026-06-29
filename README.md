# Stargazer Downloader

A lightweight video and audio downloader powered by `yt-dlp` and `FastAPI`.  
Includes a dark-themed Web UI and a Telegram Bot.

## Features
- **Web UI** — Paste link → scan → preview thumbnail → download MP4 or MP3
- **Telegram Bot** — Send link → choose format → get download link
- **Real-time progress** — Progress bar on web, status updates on Telegram
- **1000+ sites** — YouTube, TikTok, Instagram, Twitter/X, Facebook, Bilibili, Reddit, Twitch, etc.
- **Auto-cleanup** — Downloaded files expire after 10 minutes

## Why Ubuntu VPS (not Vercel)?
Vercel is **not suitable** because:
1. **Timeouts** — Free tier limits to 10-15s. Downloads take minutes.
2. **Read-only FS** — 50MB `/tmp` limit, no persistent storage.
3. **No ffmpeg** — Required for merging video/audio and MP3 conversion.

**Use an Ubuntu VPS.**

---

## Quick Deploy (Ubuntu VPS)

### 1. System Dependencies
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv ffmpeg
```

### 2. Clone & Setup
```bash
git clone https://github.com/mrfunntastiic/Stargazer-Downloader.git
cd Stargazer-Downloader
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure
```bash
cp .env.example .env
nano .env
```
```ini
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
BASE_URL=http://localhost:8000
PUBLIC_URL=http://your_vps_ip:8000
```

### 4. Run (Quick Test)
Terminal 1 — Web API:
```bash
source venv/bin/activate
python main.py
```

Terminal 2 — Telegram Bot:
```bash
source venv/bin/activate
python bot.py
```

Web UI: `http://your_vps_ip:8000`

### 5. Run with Systemd (Production)

**Web API** — `/etc/systemd/system/stargazer-web.service`:
```ini
[Unit]
Description=Stargazer Web API
After=network.target

[Service]
User=root
WorkingDirectory=/root/Stargazer-Downloader
Environment="PATH=/root/Stargazer-Downloader/venv/bin"
ExecStart=/root/Stargazer-Downloader/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

**Telegram Bot** — `/etc/systemd/system/stargazer-bot.service`:
```ini
[Unit]
Description=Stargazer Telegram Bot
After=network.target

[Service]
User=root
WorkingDirectory=/root/Stargazer-Downloader
Environment="PATH=/root/Stargazer-Downloader/venv/bin"
ExecStart=/root/Stargazer-Downloader/venv/bin/python bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

**Enable & Start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable stargazer-web stargazer-bot
sudo systemctl start stargazer-web stargazer-bot
```

### 6. (Optional) Nginx Reverse Proxy
For HTTPS with a domain:
```nginx
server {
    listen 80;
    server_name download.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 500M;
    }
}
```
Then use Certbot for SSL: `sudo certbot --nginx -d download.yourdomain.com`

## Project Structure
```
Stargazer-Downloader/
├── main.py              # FastAPI backend + yt-dlp integration
├── bot.py               # Telegram bot
├── templates/
│   └── index.html       # Web UI
├── downloads/           # Temporary download storage (auto-cleaned)
├── requirements.txt
├── .env.example
└── README.md
```

## License
MIT