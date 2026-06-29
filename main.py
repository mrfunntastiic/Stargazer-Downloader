import os
import uuid
import asyncio
import json
import time
import shutil
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Stargazer - Video Downloader")

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

templates = Jinja2Templates(directory="templates")

# Store active tasks: task_id -> {status, progress, filename, error}
tasks: dict = {}


def cleanup_old_files(max_age_seconds: int = 600):
    """Remove downloaded files older than max_age_seconds (default 10 min)."""
    now = time.time()
    for f in DOWNLOAD_DIR.iterdir():
        if f.is_file() and (now - f.stat().st_mtime) > max_age_seconds:
            f.unlink(missing_ok=True)


def extract_info(url: str) -> dict:
    """Extract video info without downloading."""
    import yt_dlp

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
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


def download_media(url: str, fmt: str, task_id: str):
    """Download video or audio using yt-dlp. Runs in thread."""
    import yt_dlp

    output_template = str(DOWNLOAD_DIR / f"{task_id}_%(title)s.%(ext)s")

    ydl_opts = {
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
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
        ydl_opts.update({
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        })

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
        tasks[task_id] = {"status": "starting", "progress": 0, "filename": None, "error": None}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Find the downloaded file
        for f in DOWNLOAD_DIR.iterdir():
            if f.name.startswith(task_id):
                tasks[task_id]["filename"] = f.name
                tasks[task_id]["status"] = "done"
                return

        tasks[task_id]["status"] = "error"
        tasks[task_id]["error"] = "File not found after download"
    except Exception as e:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["error"] = str(e)


# ─── Routes ───────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/info")
async def get_info(request: Request):
    """Get video metadata from URL."""
    body = await request.json()
    url = body.get("url", "").strip()
    if not url:
        raise HTTPException(400, "URL required")

    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, extract_info, url)
        return JSONResponse(info)
    except Exception as e:
        raise HTTPException(400, f"Failed to fetch info: {e}")


@app.post("/api/download")
async def start_download(request: Request):
    """Start a download task. Returns task_id for polling."""
    body = await request.json()
    url = body.get("url", "").strip()
    fmt = body.get("format", "video")  # "video" or "audio"

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
    """Poll download progress."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return JSONResponse(task)


@app.get("/api/file/{task_id}")
async def get_file(task_id: str):
    """Download the completed file."""
    task = tasks.get(task_id)
    if not task or task["status"] != "done":
        raise HTTPException(404, "File not ready")

    filepath = DOWNLOAD_DIR / task["filename"]
    if not filepath.exists():
        raise HTTPException(404, "File not found")

    # Clean filename (remove task_id prefix)
    clean_name = task["filename"].split("_", 1)[1] if "_" in task["filename"] else task["filename"]
    return FileResponse(filepath, filename=clean_name, media_type="application/octet-stream")


# ─── API for Telegram bot ────────────────────────────────────────

@app.post("/api/bot/download")
async def bot_download(request: Request):
    """Synchronous-style download for bot usage. Returns file path."""
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