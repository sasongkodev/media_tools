#!/usr/bin/env python3
"""
Flask Web UI for Universal Video Downloader
=============================================
Provides a beautiful web interface to download videos from any website.
"""

import os
import re
import uuid
import time
import json
import threading
from pathlib import Path
from datetime import datetime

from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory, Response, stream_with_context
)

import yt_dlp

# ─────────────────────────────────────────
# App Configuration
# ─────────────────────────────────────────
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", "media-tools-secret-key-2026")

DOWNLOAD_DIR = Path(os.environ.get("DOWNLOAD_DIR", "downloads"))
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Store active download tasks
download_tasks = {}

# ─────────────────────────────────────────
# Constants from downloader.py
# ─────────────────────────────────────────
import shutil
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

QUALITY_OPTIONS = {
    "best": "Best Quality",
    "1080p": "1080p Full HD",
    "720p": "720p HD",
    "480p": "480p SD",
    "360p": "360p Low",
    "audio": "Audio Only (MP3)",
}

_QUALITY_FORMATS_FFMPEG = {
    "best":  "bestvideo+bestaudio/best",
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p":  "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p":  "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "360p":  "bestvideo[height<=360]+bestaudio/best[height<=360]",
    "audio": "bestaudio/best",
}

_QUALITY_FORMATS_NOFFMPEG = {
    "best":  "best[ext=mp4]/best",
    "1080p": "best[height<=1080][ext=mp4]/best[height<=1080]",
    "720p":  "best[height<=720][ext=mp4]/best[height<=720]",
    "480p":  "best[height<=480][ext=mp4]/best[height<=480]",
    "360p":  "best[height<=360][ext=mp4]/best[height<=360]",
    "audio": "bestaudio/best",
}


def get_fmt(quality: str) -> str:
    pool = _QUALITY_FORMATS_FFMPEG if FFMPEG_AVAILABLE else _QUALITY_FORMATS_NOFFMPEG
    return pool.get(quality, pool["best"])


# ─────────────────────────────────────────
# Download Task Manager
# ─────────────────────────────────────────
class DownloadTask:
    def __init__(self, task_id: str, url: str, quality: str):
        self.task_id = task_id
        self.url = url
        self.quality = quality
        self.status = "pending"  # pending, extracting, downloading, completed, failed
        self.progress = 0
        self.title = "Fetching info..."
        self.filename = None
        self.filesize = None
        self.speed = None
        self.eta = None
        self.error = None
        self.thumbnail = None
        self.duration = None
        self.created_at = datetime.now().isoformat()

    def to_dict(self):
        return {
            "task_id": self.task_id,
            "url": self.url,
            "quality": self.quality,
            "status": self.status,
            "progress": self.progress,
            "title": self.title,
            "filename": self.filename,
            "filesize": self.filesize,
            "speed": self.speed,
            "eta": self.eta,
            "error": self.error,
            "thumbnail": self.thumbnail,
            "duration": self.duration,
            "created_at": self.created_at,
        }


def progress_hook(task: DownloadTask):
    """Returns a yt-dlp progress hook function for a given task."""
    def hook(d):
        if d["status"] == "downloading":
            task.status = "downloading"
            # Extract progress percentage
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                task.progress = round((downloaded / total) * 100, 1)
                task.filesize = f"{total / 1_048_576:.1f} MB"
            else:
                pct = d.get("_percent_str", "0%").strip().replace("%", "")
                try:
                    task.progress = float(pct)
                except ValueError:
                    pass

            task.speed = d.get("_speed_str", "")
            task.eta = d.get("_eta_str", "")
            task.filename = d.get("filename", "")

        elif d["status"] == "finished":
            task.status = "completed"
            task.progress = 100
            task.filename = d.get("filename", "")

    return hook


def run_download(task: DownloadTask):
    """Run the download in a background thread."""
    try:
        task.status = "extracting"
        fmt = get_fmt(task.quality)

        opts = {
            "outtmpl": str(DOWNLOAD_DIR / "%(title)s.%(ext)s"),
            "format": fmt,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "http_headers": {"User-Agent": USER_AGENT},
            "retries": 10,
            "fragment_retries": 10,
            "ignoreerrors": False,
            "geo_bypass": True,
            "progress_hooks": [progress_hook(task)],
        }

        if FFMPEG_AVAILABLE:
            opts["merge_output_format"] = "mp4"

        if task.quality == "audio":
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]

        with yt_dlp.YoutubeDL(opts) as ydl:
            # First extract info
            info_dict = ydl.extract_info(task.url, download=False)
            if info_dict:
                task.title = info_dict.get("title", "Unknown")
                task.thumbnail = info_dict.get("thumbnail", "")
                duration = info_dict.get("duration")
                if duration:
                    mins, secs = divmod(int(duration), 60)
                    hours, mins = divmod(mins, 60)
                    if hours:
                        task.duration = f"{hours}:{mins:02d}:{secs:02d}"
                    else:
                        task.duration = f"{mins}:{secs:02d}"

            # Now download
            task.status = "downloading"
            ydl.download([task.url])

        task.status = "completed"
        task.progress = 100

    except Exception as e:
        task.status = "failed"
        task.error = str(e)


# ─────────────────────────────────────────
# Flask Routes
# ─────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html",
                           quality_options=QUALITY_OPTIONS,
                           ffmpeg_available=FFMPEG_AVAILABLE)


@app.route("/api/download", methods=["POST"])
def start_download():
    """Start a new download task."""
    data = request.get_json()
    url = data.get("url", "").strip()
    quality = data.get("quality", "best")

    if not url:
        return jsonify({"error": "URL is required"}), 400
    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "Invalid URL. Must start with http:// or https://"}), 400
    if quality not in QUALITY_OPTIONS:
        quality = "best"

    task_id = str(uuid.uuid4())[:8]
    task = DownloadTask(task_id, url, quality)
    download_tasks[task_id] = task

    # Start download in background thread
    thread = threading.Thread(target=run_download, args=(task,), daemon=True)
    thread.start()

    return jsonify({"task_id": task_id, "message": "Download started"})


@app.route("/api/status/<task_id>")
def get_status(task_id):
    """Get the status of a download task."""
    task = download_tasks.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(task.to_dict())


@app.route("/api/tasks")
def list_tasks():
    """List all download tasks."""
    tasks = [t.to_dict() for t in reversed(list(download_tasks.values()))]
    return jsonify(tasks)


@app.route("/api/info", methods=["POST"])
def get_video_info():
    """Extract video info without downloading."""
    data = request.get_json()
    url = data.get("url", "").strip()

    if not url:
        return jsonify({"error": "URL is required"}), 400

    try:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "http_headers": {"User-Agent": USER_AGENT},
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                formats = []
                for f in (info.get("formats") or []):
                    fmt_info = {
                        "format_id": f.get("format_id", ""),
                        "ext": f.get("ext", ""),
                        "resolution": f.get("resolution", ""),
                        "filesize": f"{f['filesize'] / 1_048_576:.1f} MB" if f.get("filesize") else "N/A",
                        "vcodec": f.get("vcodec", ""),
                        "acodec": f.get("acodec", ""),
                    }
                    formats.append(fmt_info)

                return jsonify({
                    "title": info.get("title", "Unknown"),
                    "thumbnail": info.get("thumbnail", ""),
                    "duration": info.get("duration"),
                    "uploader": info.get("uploader", ""),
                    "view_count": info.get("view_count"),
                    "description": (info.get("description") or "")[:300],
                    "formats": formats[:20],
                })
        return jsonify({"error": "Could not extract info"}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/files")
def list_files():
    """List downloaded files."""
    files = []
    if DOWNLOAD_DIR.exists():
        for f in sorted(DOWNLOAD_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.is_file() and not f.name.startswith("."):
                stat = f.stat()
                files.append({
                    "name": f.name,
                    "size": f"{stat.st_size / 1_048_576:.1f} MB",
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "ext": f.suffix.lower(),
                })
    return jsonify(files)


@app.route("/api/files/<filename>/delete", methods=["DELETE"])
def delete_file(filename):
    """Delete a downloaded file."""
    filepath = DOWNLOAD_DIR / filename
    if filepath.exists() and filepath.is_file():
        filepath.unlink()
        return jsonify({"message": f"Deleted {filename}"})
    return jsonify({"error": "File not found"}), 404


@app.route("/downloads/<path:filename>")
def serve_download(filename):
    """Serve a downloaded file."""
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)


@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "ffmpeg": FFMPEG_AVAILABLE,
        "download_dir": str(DOWNLOAD_DIR.resolve()),
        "active_tasks": len([t for t in download_tasks.values() if t.status in ("pending", "extracting", "downloading")]),
    })


# ─────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    print(f"\n🚀 Media Tools Web UI running at http://0.0.0.0:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=debug)
