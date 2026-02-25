#!/usr/bin/env python3
"""
Universal Video Downloader
===========================
Download video dari website apapun hanya dengan paste link!

Didukung (1000+ website via yt-dlp):
  YouTube, TikTok, Instagram, Facebook, Twitter/X, Vimeo,
  Dailymotion, Twitch, Reddit, Bilibili, WordPress, Blogger,
  situs berita, streaming dewasa, dan ratusan lainnya.

Fallback:
  Scraping HTML untuk situs yang tidak dikenal.

Cara cepat:
  ./run.sh                         → mode interaktif
  ./run.sh -u URL                  → download satu URL
  ./run.sh --batch links.txt       → download banyak URL
  ./run.sh -u URL -q best          → pilih kualitas video
  ./run.sh -u URL -p http://proxy:port   → pakai proxy
  ./run.sh -u URL --cookies cookies.txt  → pakai cookies
"""

import os
import re
import sys
import time
import argparse
import urllib.parse
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
import yt_dlp
import shutil

# Playwright (opsional – hanya diimport jika dibutuhkan)
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Deteksi ffmpeg sekali saat startup
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None

# ─────────────────────────────────────────
# Konstanta
# ─────────────────────────────────────────
DOWNLOAD_DIR    = Path("downloads")
VIDEO_EXTS      = {".mp4", ".webm", ".ogg", ".mov", ".avi", ".mkv", ".flv", ".m4v", ".ts", ".wmv", ".3gp"}
USER_AGENT      = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# Format dengan ffmpeg (bisa merge video+audio terpisah)
_QUALITY_FORMATS_FFMPEG = {
    "best":   "bestvideo+bestaudio/best",
    "1080p":  "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p":   "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p":   "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "360p":   "bestvideo[height<=360]+bestaudio/best[height<=360]",
    "audio":  "bestaudio/best",
    "worst":  "worstvideo+worstaudio/worst",
}

# Format tanpa ffmpeg (single-file pre-merged, kualitas sedikit lebih rendah)
_QUALITY_FORMATS_NOFFMPEG = {
    "best":   "best[ext=mp4]/best",
    "1080p":  "best[height<=1080][ext=mp4]/best[height<=1080]",
    "720p":   "best[height<=720][ext=mp4]/best[height<=720]",
    "480p":   "best[height<=480][ext=mp4]/best[height<=480]",
    "360p":   "best[height<=360][ext=mp4]/best[height<=360]",
    "audio":  "bestaudio/best",
    "worst":  "worst[ext=mp4]/worst",
}

def get_fmt(quality: str) -> str:
    """Pilih format string sesuai ketersediaan ffmpeg."""
    pool = _QUALITY_FORMATS_FFMPEG if FFMPEG_AVAILABLE else _QUALITY_FORMATS_NOFFMPEG
    return pool.get(quality, pool["best"])

# Alias untuk argparse choices
QUALITY_FORMATS = _QUALITY_FORMATS_FFMPEG


# Platform yang pasti didukung yt-dlp — jangan fallback ke scraping
KNOWN_PLATFORMS = {
    "youtube.com", "youtu.be", "tiktok.com", "instagram.com",
    "facebook.com", "fb.watch", "twitter.com", "x.com",
    "vimeo.com", "dailymotion.com", "twitch.tv", "reddit.com",
    "bilibili.com", "rumble.com", "odysee.com", "niconico.jp",
    "nicovideo.jp", "ok.ru", "streamable.com", "ted.com",
    "soundcloud.com", "bandcamp.com", "tumblr.com",
}

# Situs yang memerlukan browser headless (JS-rendered, iframe/API encrypted)
# Playwright akan dipakai untuk intercept network request m3u8/mp4
BROWSER_SITES = {
    "liveomek.com", "omek.live",
    "bysedikamoum.com", "f75s.com",
    "nonton17.com", "viralstreamxx.com",
    "bokepsin.com", "bokepviral.com",
    "videomesum.net", "viralindo.net",
}


# ─────────────────────────────────────────
# Terminal warna
# ─────────────────────────────────────────
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    CYAN    = "\033[96m"
    MAGENTA = "\033[95m"
    BLUE    = "\033[94m"
    DIM     = "\033[2m"

def info(msg):    print(f"{C.CYAN}[INFO]{C.RESET}  {msg}")
def ok(msg):      print(f"{C.GREEN}[OK]{C.RESET}    {msg}")
def warn(msg):    print(f"{C.YELLOW}[WARN]{C.RESET}  {msg}")
def err(msg):     print(f"{C.RED}[ERROR]{C.RESET} {msg}")
def sep():        print(f"{C.DIM}{'─' * 55}{C.RESET}")


def banner():
    ffmpeg_status = f"{C.GREEN}✓ ffmpeg{C.RESET}" if FFMPEG_AVAILABLE else f"{C.YELLOW}✗ ffmpeg (kualitas terbatas){C.RESET}"
    print(f"""
{C.CYAN}{C.BOLD}╔═══════════════════════════════════════════════╗
║        Universal Video Downloader v2.1        ║
║   Paste link dari website apapun → Download!  ║
║   1000+ situs didukung via yt-dlp             ║
╚═══════════════════════════════════════════════╝{C.RESET}
  Status : {ffmpeg_status}
""")


# ─────────────────────────────────────────
# Utilitas
# ─────────────────────────────────────────
def sanitize(name: str, max_len: int = 120) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    name = name.strip(". ")
    return name[:max_len] or "video"


def make_session(proxy: str | None = None) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    if proxy:
        s.proxies = {"http": proxy, "https": proxy}
    return s


# ─────────────────────────────────────────
# 1. Download file video langsung (direct)
# ─────────────────────────────────────────
def download_direct(url: str, dest_dir: Path,
                    session: requests.Session,
                    filename: str | None = None) -> bool:
    try:
        resp = session.get(url, stream=True, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        err(f"Direct download gagal: {e}")
        return False

    # Tentukan nama file
    if not filename:
        cd = resp.headers.get("content-disposition", "")
        m  = re.search(r'filename=["\']?([^"\';\r\n]+)', cd)
        filename = m.group(1).strip() if m else urllib.parse.unquote(url.split("?")[0].rstrip("/").split("/")[-1])
        filename = filename or f"video_{int(time.time())}.mp4"

    filename = sanitize(filename)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    if dest.exists():
        stem, suf = dest.stem, dest.suffix
        dest = dest_dir / f"{stem}_{int(time.time())}{suf}"

    total = int(resp.headers.get("content-length", 0))
    info(f"File    : {C.BOLD}{filename}{C.RESET}")
    info(f"Ukuran  : {total/1_048_576:.2f} MB" if total else "Ukuran  : -")

    with open(dest, "wb") as f, tqdm(
        total=total, unit="B", unit_scale=True, unit_divisor=1024,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{rate_fmt}]"
    ) as bar:
        for chunk in resp.iter_content(8192):
            f.write(chunk)
            bar.update(len(chunk))

    ok(f"Tersimpan: {C.BOLD}{dest}{C.RESET}")
    return True


# ─────────────────────────────────────────
# 2. Download via yt-dlp (engine utama)
# ─────────────────────────────────────────
def download_ytdlp(url: str, dest_dir: Path,
                   quality: str = "best",
                   proxy:   str | None = None,
                   cookies: str | None = None) -> bool:
    dest_dir.mkdir(parents=True, exist_ok=True)
    fmt = get_fmt(quality)


    opts: dict = {
        "outtmpl":             str(dest_dir / "%(title)s.%(ext)s"),
        "format":              fmt,
        "quiet":               False,
        "no_warnings":         False,
        "noplaylist":          True,
        "http_headers":        {"User-Agent": USER_AGENT},
        "retries":             10,
        "fragment_retries":    10,
        "ignoreerrors":        False,
        "geo_bypass":          True,
    }

    # merge_output_format + HLS via ffmpeg jika tersedia
    if FFMPEG_AVAILABLE:
        opts["merge_output_format"] = "mp4"
        opts["external_downloader"] = "ffmpeg"
        opts["external_downloader_args"] = ["-loglevel", "warning"]
        opts["hls_use_mpegts"] = True

    if proxy:
        opts["proxy"] = proxy
    if cookies and Path(cookies).exists():
        opts["cookiefile"] = cookies

    # Jika kualitas audio-only → tambah postprocessor konversi mp3
    if quality == "audio":
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
        opts["outtmpl"] = str(dest_dir / "%(title)s.%(ext)s")

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            title = info_dict.get("title", "video") if info_dict else "video"
            ok(f"Download selesai: {C.BOLD}{title}{C.RESET}")
        return True
    except yt_dlp.utils.DownloadError as e:
        err(f"yt-dlp gagal: {e}")
        return False


# ─────────────────────────────────────────
# 3. Scraping HTML fallback (situs custom)
# ─────────────────────────────────────────
def scrape_page(page_url: str, session: requests.Session) -> list[dict]:
    """Temukan semua sumber video di halaman HTML manapun."""
    found: list[dict] = []
    try:
        resp = session.get(page_url, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        err(f"Tidak bisa membuka halaman: {e}")
        return found

    soup = BeautifulSoup(resp.text, "lxml")
    base = "{uri.scheme}://{uri.netloc}".format(uri=urllib.parse.urlparse(page_url))

    def add(url: str, label: str, kind: str = "direct"):
        url = url.strip()
        if url:
            found.append({"url": urllib.parse.urljoin(base, url), "label": label, "kind": kind})

    # <video src> dan <source src>
    for v in soup.find_all("video"):
        if v.get("src"): add(v["src"], "video[src]")
        for s in v.find_all("source"):
            if s.get("src"): add(s["src"], "video>source")

    # <a href> ke file video
    for a in soup.find_all("a", href=True):
        ext = Path(urllib.parse.urlparse(a["href"]).path).suffix.lower()
        if ext in VIDEO_EXTS:
            add(a["href"], f"a[href]{ext}")

    # <iframe> embed (YouTube, Vimeo, dll)
    for iframe in soup.find_all("iframe", src=True):
        src = iframe["src"]
        if any(d in src for d in ["youtube", "youtu.be", "vimeo", "dailymotion",
                                   "videopress", "rumble", "odysee", "ok.ru"]):
            add(src, "iframe-embed", "embed")

    # data-* attributes
    for tag in soup.find_all(True):
        for attr, val in tag.attrs.items():
            if isinstance(val, str) and attr.startswith("data-") and val.startswith("http"):
                ext = Path(urllib.parse.urlparse(val).path).suffix.lower()
                if ext in VIDEO_EXTS:
                    add(val, f"data[{attr}]")

    # URL video di dalam teks <script>
    for script in soup.find_all("script"):
        raw = script.get_text()
        for url in re.findall(r'https?://[^\s"\',]+\.(?:mp4|webm|m3u8|m4v|mov|flv|ts)\b[^\s"\']*', raw, re.I):
            add(url, "script/json")
        # HLS / DASH manifest
        for url in re.findall(r'https?://[^\s"\']+\.m3u8[^\s"\']*', raw):
            add(url, "HLS-m3u8", "stream")

    # og:video meta — hanya property 'og:video' persis (bukan og:video:type dll)
    for meta in soup.find_all("meta", {"property": "og:video"}):
        content = meta.get("content", "").strip()
        if content.startswith("http"):
            add(content, "og:video")

    # Hapus duplikat
    seen: set[str] = set()
    unique = []
    for item in found:
        if item["url"] not in seen:
            seen.add(item["url"])
            unique.append(item)
    return unique


# ─────────────────────────────────────────
# 4. Browser-based scraping (Playwright)
# ─────────────────────────────────────────
def scrape_with_browser(page_url: str, timeout: int = 30) -> list[dict]:
    """
    Buka halaman dengan Chromium headless, intercept semua network request,
    dan kumpulkan URL yang mengandung .m3u8, .mp4, atau pola stream lainnya.
    Juga ikuti iframe bersarang (max 2 level).
    """
    if not PLAYWRIGHT_AVAILABLE:
        warn("playwright tidak terinstall. Jalankan: pip install playwright && python -m playwright install chromium")
        return []

    found: list[dict] = []
    seen: set[str] = set()

    STREAM_PATTERNS = re.compile(
        r'\.(m3u8|mpd|mp4|webm|m4v|mov|flv|ts)(\?|$)', re.I
    )

    def collect(url: str, label: str, kind: str = "stream"):
        url = url.split("?")[0] + ("?" + url.split("?")[1] if "?" in url else "")
        if url not in seen and len(url) < 2000:
            seen.add(url)
            found.append({"url": url, "label": label, "kind": kind})

    info("→ Membuka browser headless (Playwright)...")
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                ]
            )
            ctx = browser.new_context(
                user_agent=USER_AGENT,
                ignore_https_errors=True,
            )

            def on_request(req):
                u = req.url
                if STREAM_PATTERNS.search(u):
                    ext = re.search(r'\.(m3u8|mpd|mp4|webm|m4v|ts|flv)', u, re.I)
                    label = ext.group(0).lstrip(".").upper() if ext else "stream"
                    collect(u, f"network/{label}")

            # ── Halaman utama ──────────────────────────────────────────────
            page = ctx.new_page()
            page.on("request", on_request)
            try:
                page.goto(page_url, wait_until="networkidle", timeout=timeout * 1000)
            except PWTimeout:
                warn("Timeout networkidle, mencoba dengan load...")
                try:
                    page.goto(page_url, wait_until="load", timeout=timeout * 1000)
                    page.wait_for_timeout(5000)
                except Exception:
                    pass

            # Cari iframe di halaman utama dan ikuti
            iframe_urls: list[str] = []
            for iframe in page.query_selector_all("iframe[src]"):
                try:
                    src = iframe.get_attribute("src") or ""
                    if src.startswith("http"):
                        iframe_urls.append(src)
                except Exception:
                    pass

            # ── Buka iframe level 1 ───────────────────────────────────────
            for iframe_url in iframe_urls:
                info(f"  → Membuka iframe: {iframe_url[:70]}")
                iframe_page = ctx.new_page()
                iframe_page.on("request", on_request)
                try:
                    iframe_page.goto(iframe_url, wait_until="networkidle", timeout=timeout * 1000)
                except PWTimeout:
                    try:
                        iframe_page.goto(iframe_url, wait_until="load", timeout=timeout * 1000)
                        iframe_page.wait_for_timeout(6000)
                    except Exception:
                        pass
                except Exception as e:
                    warn(f"  Iframe gagal dibuka: {e}")
                finally:
                    iframe_page.close()

            page.close()
            ctx.close()
            browser.close()

    except Exception as e:
        err(f"Browser scraping error: {e}")

    # Filter: utamakan master.m3u8 di atas index.m3u8
    m3u8_found = [f for f in found if "m3u8" in f["url"].lower()]
    others     = [f for f in found if "m3u8" not in f["url"].lower()]
    master     = [f for f in m3u8_found if "master" in f["url"].lower()]
    non_master = [f for f in m3u8_found if "master" not in f["url"].lower()]
    return master + non_master + others


# ─────────────────────────────────────────
# Logika pemilihan metode download
# ─────────────────────────────────────────
def process_url(url: str, dest_dir: Path,
                quality: str = "best",
                proxy:   str | None = None,
                cookies: str | None = None,
                no_scrape: bool = False):
    url = url.strip()
    if not url:
        return

    sep()
    info(f"URL : {C.BOLD}{url[:80]}{C.RESET}")

    session = make_session(proxy)

    # ── Kasus 1: URL adalah file video langsung ──────────────────
    parsed_path = Path(urllib.parse.urlparse(url).path)
    if parsed_path.suffix.lower() in VIDEO_EXTS:
        info("→ File video langsung, download direct.")
        download_direct(url, dest_dir, session)
        return

    # ── Kasus 2: HLS / DASH stream ───────────────────────────────
    if parsed_path.suffix.lower() in (".m3u8", ".mpd"):
        info("→ Streaming manifest (HLS/DASH), download via yt-dlp.")
        download_ytdlp(url, dest_dir, quality, proxy, cookies)
        return

    # ── Kasus 3: Platform yang dikenal → yt-dlp verbose, TANPA scraping ─
    netloc = urllib.parse.urlparse(url).netloc.lower()
    parsed_host = netloc.removeprefix("www.")
    is_known = any(parsed_host == p or parsed_host.endswith("." + p) for p in KNOWN_PLATFORMS)

    if is_known:
        info(f"→ Platform dikenal ({parsed_host}), download via yt-dlp...")
        download_ytdlp(url, dest_dir, quality, proxy, cookies)
        return

    # ── Kasus 4: Situs lain → coba yt-dlp diam-diam dulu ────────
    info("→ Mencoba yt-dlp (1000+ situs didukung)...")
    success = _try_ytdlp(url, dest_dir, quality, proxy, cookies)
    if success:
        return

    # ── Kasus 5: Cek apakah situs butuh browser headless ─────────
    is_browser_site = any(
        parsed_host == b or parsed_host.endswith("." + b) for b in BROWSER_SITES
    )

    if no_scrape:
        warn("yt-dlp gagal dan --no-scrape aktif, melewati scraping.")
        return

    # ── Kasus 6: Browser scraping (untuk situs JS-heavy) ─────────
    if is_browser_site and PLAYWRIGHT_AVAILABLE:
        info("→ Situs membutuhkan browser headless, menggunakan Playwright...")
        videos = scrape_with_browser(url)
        if not videos:
            warn("Browser scraping tidak menemukan stream. Coba scraping HTML biasa...")
            videos = scrape_page(url, session)
    else:
        # ── Kasus 7: Fallback scraping HTML biasa ─────────────────
        info("→ yt-dlp tidak bisa, coba scraping halaman HTML...")
        videos = scrape_page(url, session)

        # Jika HTML biasa gagal, coba browser sebagai last resort
        if not videos and PLAYWRIGHT_AVAILABLE:
            info("→ HTML scraping kosong, mencoba browser headless sebagai last resort...")
            videos = scrape_with_browser(url)

    if not videos:
        warn("Tidak ada video ditemukan di halaman.")
        if not PLAYWRIGHT_AVAILABLE:
            warn(f"Tip: Install playwright untuk situs JS-heavy: {C.BOLD}pip install playwright && python -m playwright install chromium{C.RESET}")
        return

    # Pisahkan stream m3u8 dari video lainnya
    m3u8_videos = [v for v in videos if "m3u8" in v["url"].lower()]
    other_videos = [v for v in videos if "m3u8" not in v["url"].lower() and v["label"] != "network/TS"]

    print(f"\n{C.GREEN}Ditemukan {len(videos)} sumber video:{C.RESET}")
    for i, v in enumerate(videos, 1):
        print(f"  {C.BOLD}[{i}]{C.RESET} {C.DIM}[{v['label']}]{C.RESET} {v['url'][:80]}")

    # Auto-pilih master.m3u8 jika ada (dari browser scraping)
    if is_browser_site and m3u8_videos:
        master = next((v for v in m3u8_videos if "master" in v["url"].lower()), m3u8_videos[0])
        info(f"→ Auto-download stream terbaik: {master['url'][:70]}")
        download_ytdlp(master["url"], dest_dir, quality, proxy, cookies)
        return

    if len(videos) == 1:
        choice = [1]
    else:
        raw = input(f"\nDownload nomor berapa? (contoh: 1,3 | 'all' | Enter=semua): ").strip()
        if raw.lower() in ("", "all", "semua"):
            choice = list(range(1, len(videos) + 1))
        else:
            choice = [int(x) for x in raw.split(",") if x.strip().isdigit()]

    for idx in choice:
        if not (1 <= idx <= len(videos)):
            continue
        v = videos[idx - 1]
        info(f"Mengunduh #{idx}: {v['url'][:70]}")
        if v["kind"] in ("embed", "stream"):
            download_ytdlp(v["url"], dest_dir, quality, proxy, cookies)
        else:
            ok_dl = download_direct(v["url"], dest_dir, session)
            if not ok_dl:
                info("Mencoba via yt-dlp sebagai fallback...")
                download_ytdlp(v["url"], dest_dir, quality, proxy, cookies)


def _try_ytdlp(url: str, dest_dir: Path,
               quality: str, proxy: str | None, cookies: str | None) -> bool:
    """Jalankan yt-dlp dengan quiet=True dulu; jika gagal kembalikan False."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    fmt = get_fmt(quality)
    opts = {
        "outtmpl":             str(dest_dir / "%(title)s.%(ext)s"),
        "format":              fmt,
        "quiet":               True,
        "no_warnings":         True,
        "noplaylist":          True,
        "http_headers":        {"User-Agent": USER_AGENT},
        "retries":             3,
        "ignoreerrors":        False,
        "geo_bypass":          True,
    }
    if FFMPEG_AVAILABLE:
        opts["merge_output_format"] = "mp4"
    if proxy:   opts["proxy"] = proxy
    if cookies and Path(cookies).exists():
        opts["cookiefile"] = cookies

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
        title = info_dict.get("title", "video") if info_dict else "video"
        ok(f"Download selesai: {C.BOLD}{title}{C.RESET}")
        return True
    except yt_dlp.utils.DownloadError:
        return False
    except Exception:
        return False


# ─────────────────────────────────────────
# Mode interaktif
# ─────────────────────────────────────────
def interactive_mode(dest_dir: Path, quality: str, proxy: str | None, cookies: str | None):
    banner()
    print(f"  Simpan ke     : {C.BOLD}{dest_dir.resolve()}{C.RESET}")
    print(f"  Kualitas      : {C.BOLD}{quality}{C.RESET}")
    if proxy:   print(f"  Proxy         : {C.BOLD}{proxy}{C.RESET}")
    if cookies: print(f"  Cookies file  : {C.BOLD}{cookies}{C.RESET}")
    print(f"\n  Ketik {C.YELLOW}'exit'{C.RESET} untuk keluar, {C.YELLOW}'quality'{C.RESET} untuk ganti kualitas.\n")

    current_quality = quality
    while True:
        try:
            raw = input(f"{C.MAGENTA}🔗 Paste URL: {C.RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{C.YELLOW}Keluar...{C.RESET}")
            break

        if not raw:
            continue

        if raw.lower() in ("exit", "quit", "keluar", "q"):
            print(f"{C.YELLOW}Sampai jumpa!{C.RESET}")
            break

        # Perintah ganti kualitas
        if raw.lower() == "quality":
            print(f"  Pilihan: {', '.join(QUALITY_FORMATS.keys())}")
            q = input("  Kualitas baru: ").strip().lower()
            if q in QUALITY_FORMATS:
                current_quality = q
                ok(f"Kualitas diubah ke: {current_quality}")
            else:
                warn("Kualitas tidak valid.")
            continue

        if not raw.startswith(("http://", "https://")):
            err("URL tidak valid. Harus diawali http:// atau https://")
            continue

        process_url(raw, dest_dir, current_quality, proxy, cookies)
        print()


# ─────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        prog="downloader",
        description="Universal Video Downloader – download video dari website apapun!",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Contoh:
  python downloader.py                             # mode interaktif
  python downloader.py -u https://youtube.com/watch?v=xxx
  python downloader.py -u https://tiktok.com/@user/video/xxx
  python downloader.py -u https://sitewp.com/post/ -q 720p
  python downloader.py -u URL -p http://proxy:8080
  python downloader.py -u URL --cookies cookies.txt
  python downloader.py --batch links.txt -q best

Pilihan kualitas: {', '.join(QUALITY_FORMATS.keys())}
        """
    )
    parser.add_argument("-u", "--url",      help="URL halaman atau file video langsung")
    parser.add_argument("-o", "--output",   default=str(DOWNLOAD_DIR), help="Folder tujuan (default: ./downloads)")
    parser.add_argument("-q", "--quality",  default="best", choices=list(QUALITY_FORMATS.keys()),
                        help="Kualitas video (default: best)")
    parser.add_argument("-p", "--proxy",    help="Proxy URL (contoh: http://127.0.0.1:8080)")
    parser.add_argument("--cookies",        metavar="FILE", help="File cookies.txt untuk login")
    parser.add_argument("--batch",          metavar="FILE", help="File teks berisi daftar URL (satu per baris)")
    parser.add_argument("--no-scrape",      action="store_true", help="Nonaktifkan fallback scraping HTML")
    parser.add_argument("--list-sites",     action="store_true", help="Tampilkan 30 situs populer yang didukung yt-dlp")
    args = parser.parse_args()

    if args.list_sites:
        sites = [
            "YouTube", "YouTube Playlist/Channel", "TikTok", "Instagram", "Facebook",
            "Twitter/X", "Vimeo", "Dailymotion", "Twitch", "Reddit", "Bilibili",
            "Rumble", "Odysee", "Niconico", "Crunchyroll", "SoundCloud", "Bandcamp",
            "Mixcloud", "Ted.com", "BBC", "CNN", "ABC News", "Tumblr", "Pinterest",
            "LinkedIn", "Telegram (t.me)", "OK.ru (VK)", "Weibo", "Streamable", "Gfycat",
            "WordPress (scraping)", "Blogger/Blogspot (scraping)", "Situs custom (scraping HTML)",
        ]
        print(f"\n{C.BOLD}Situs yang didukung (sebagian kecil):{C.RESET}")
        for i, s in enumerate(sites, 1):
            print(f"  {i:2}. {s}")
        print(f"\n  ... dan 1000+ situs lainnya via yt-dlp.\n")
        return

    dest    = Path(args.output)
    quality = args.quality
    proxy   = args.proxy
    cookies = args.cookies

    if args.batch:
        batch_file = Path(args.batch)
        if not batch_file.exists():
            err(f"File tidak ditemukan: {batch_file}")
            sys.exit(1)
        urls = [l.strip() for l in batch_file.read_text().splitlines()
                if l.strip() and not l.startswith("#")]
        banner()
        info(f"Batch mode: {len(urls)} URL")
        for u in urls:
            process_url(u, dest, quality, proxy, cookies, args.no_scrape)
        ok("Semua URL selesai diproses!")

    elif args.url:
        banner()
        process_url(args.url, dest, quality, proxy, cookies, args.no_scrape)

    else:
        interactive_mode(dest, quality, proxy, cookies)


if __name__ == "__main__":
    main()
