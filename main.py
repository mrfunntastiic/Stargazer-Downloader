import os
import uuid
import asyncio
import time
import re
import urllib.request
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Stargazer - Video Downloader")

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

templates = Jinja2Templates(directory="templates")

tasks: dict = {}

# ── Config: shared yt-dlp options ─────────────────────────────---

def _ytdlp_base_opts() -> dict:
    """Base options for yt-dlp — always tries OAuth2 for YouTube."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "username": "oauth2",
        "password": "",
    }
    if os.path.exists("cookies.txt"):
        opts["cookiefile"] = "cookies.txt"
    return opts


# ── Metadata extract ──────────────────────────────────────────────

def extract_info(url: str) -> dict:
    import yt_dlp
    ydl_opts = {**_ytdlp_base_opts(), "skip_download": True, "format": None}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "title": info.get("title", "Unknown"),
                "thumbnail": info.get("thumbnail", ""),
                "duration": info.get("duration", 0),
                "uploader": info.get("uploader", "Unknown"),
                "url": url,
                "formats_available": True,
            }
    except Exception as e:
        # Fallback: quick scrape for title/thumb
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            title = ""
            thumb = ""
            m = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html)
            if m:
                title = m.group(1)
            else:
                m = re.search(r"<title>([^<]+)", html)
                if m:
                    title = m.group(1).strip()
            m = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
            if m:
                thumb = m.group(1)
            return {
                "title": title or "Video",
                "thumbnail": thumb,
                "duration": 0,
                "uploader": "",
                "url": url,
                "formats_available": True,
            }
        except Exception:
            raise HTTPException(400, f"Failed to fetch info: {e}")


# ── Download ──────────────────────────────────────────────────────

def download_media(url: str, fmt: str, task_id: str):
    import yt_dlp

    tasks[task_id] = {"status": "starting", "progress": 0, "filename": None, "error": None}

    output_template = str(DOWNLOAD_DIR / f"{task_id}_%(title)s.%(ext)s")
    ydl_opts = {
        **_ytdlp_base_opts(),
        "outtmpl": output_template,
        "merge_output_format": "mp4" if fmt == "video" else None,
    }

    if fmt == "audio":
        ydl_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
    else:
        ydl_opts.update({"format": "bestvideo+bestaudio/best"})

    def progress_hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                tasks[task_id]["progress"] = round(downloaded / total * 100, 1)
            tasks[task_id]["status"] = "downloading"
        elif d["status"] == "finished":
            tasks[task_id]["status"] = "processing"
            tasks[task_id]["progress"] = 100

    ydl_opts["progress_hooks"] = [progress_hook]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        for f in DOWNLOAD_DIR.iterdir():
            if f.name.startswith(task_id):
                tasks[task_id]["filename"] = f.name
                tasks[task_id]["status"] = "done"
                tasks[task_id]["progress"] = 100
                return
        tasks[task_id]["error"] = "yt-dlp finished but file not found"
    except Exception as e:
        tasks[task_id]["error"] = str(e)

    if tasks[task_id]["status"] != "done":
        tasks[task_id]["status"] = "error"


# ── Cleanup old files ────────────────────────────────────────────

def cleanup_old_files(max_age_seconds: int = 600):
    now = time.time()
    for f in DOWNLOAD_DIR.iterdir():
        if f.is_file() and (now - f.stat().st_mtime) > max_age_seconds:
            f.unlink(missing_ok=True)


# ── Routes ────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/api/info")
async def get_info(request: Request):
    body = await request.json()
    url = body.get("url", "").strip()
    if not url:
        raise HTTPException(400, "URL required")
    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(None, extract_info, url)
    return JSONResponse(info)


@app.post("/api/download")
async def start_download(request: Request):
    body = await request.json()
    url = body.get("url", "").strip()
    fmt = body.get("format", "video")
    if not url:
        raise HTTPException(400, "URL required")
    if fmt not in ("video", "audio"):
        raise HTTPException(400, "Format must be 'video' or 'audio'")
    cleanup_old_files()
    task_id = uuid.uuid4().hex[:12]
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, download_media, url, fmt, task_id)
    return JSONResponse({"task_id": task_id})


@app.get("/api/status/{task_id}")
async def check_status(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return JSONResponse(task)


@app.get("/api/file/{task_id}")
async def get_file(task_id: str):
    task = tasks.get(task_id)
    if not task or task["status"] != "done":
        raise HTTPException(404, "File not ready")
    filepath = DOWNLOAD_DIR / task["filename"]
    if not filepath.exists():
        raise HTTPException(404, "File not found")
    clean_name = task["filename"].split("_", 1)[1] if "_" in task["filename"] else task["filename"]
    return FileResponse(filepath, filename=clean_name, media_type="application/octet-stream")


@app.post("/api/bot/download")
async def bot_download(request: Request):
    body = await request.json()
    url = body.get("url", "").strip()
    fmt = body.get("format", "video")
    if not url:
        raise HTTPException(400, "URL required")
    cleanup_old_files()
    task_id = uuid.uuid4().hex[:12]
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, download_media, url, fmt, task_id)
    task = tasks.get(task_id)
    if not task or task["status"] != "done":
        error_msg = task.get("error", "Unknown error") if task else "Task failed"
        raise HTTPException(500, f"Download failed: {error_msg}")
    return JSONResponse({
        "task_id": task_id,
        "filename": task["filename"],
        "download_url": f"/api/file/{task_id}",
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)