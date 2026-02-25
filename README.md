# Universal Video Downloader 🎬

Download video dari **website apapun** hanya dengan paste link!  
Ditenagai **yt-dlp** (1000+ situs) + fallback scraping HTML untuk situs custom.

---

## ✨ Fitur

| Fitur              | Keterangan                                                       |
| ------------------ | ---------------------------------------------------------------- |
| 🌐 1000+ situs     | YouTube, TikTok, Instagram, FB, Twitter/X, Vimeo, dll via yt-dlp |
| 🔍 Scraping HTML   | Fallback untuk situs apapun (WordPress, custom CMS, dll)         |
| 📹 Direct download | File `.mp4`, `.webm`, dll langsung diunduh dengan progress bar   |
| 🎚️ Pilih kualitas  | best / 1080p / 720p / 480p / 360p / audio-only                   |
| 🔒 Proxy support   | `-p http://proxy:port`                                           |
| 🍪 Cookie support  | `--cookies cookies.txt` untuk situs yang butuh login             |
| 📋 Batch mode      | Download banyak URL sekaligus dari file teks                     |
| 🔁 Auto-retry      | Retry otomatis jika koneksi terputus                             |

---

## 🚀 Instalasi

Sudah dibuat virtual environment dengan semua library terinstall.

```bash
cd ~/Desktop/vid
```

---

## 🎮 Cara Penggunaan

### Mode interaktif (paling mudah)

```bash
./run.sh
```

Paste URL → Enter → video didownload. Ketik `exit` untuk keluar.

### Satu URL langsung

```bash
./run.sh -u https://youtube.com/watch?v=xxx
./run.sh -u https://tiktok.com/@user/video/xxx
./run.sh -u https://sitewp.com/post/dengan-video/
./run.sh -u https://sitewp.com/wp-content/video.mp4
```

### Pilih kualitas

```bash
./run.sh -u URL -q 720p
./run.sh -u URL -q audio      # audio-only → mp3
```

### Gunakan proxy (untuk situs yang diblokir ISP)

```bash
./run.sh -u URL -p http://127.0.0.1:8080
```

### Login dengan cookies

```bash
# Export cookies dari browser (pakai ekstensi: Get cookies.txt)
./run.sh -u URL --cookies cookies.txt
```

### Batch – banyak URL sekaligus

```bash
# Buat file links.txt (satu URL per baris, # = komentar)
./run.sh --batch links.txt -q 720p
```

### Lihat situs yang didukung

```bash
./run.sh --list-sites
```

---

## ⚙️ Cara Kerja (Otomatis)

```
URL di-paste
     │
     ├─► File video langsung (.mp4/.webm)? → Direct download
     │
     ├─► HLS/DASH stream (.m3u8/.mpd)?    → yt-dlp stream download
     │
     ├─► yt-dlp bisa handle?              → yt-dlp download (1000+ situs)
     │
     └─► Scraping HTML fallback           → temukan <video>, <source>, mp4 links
```

---

## 📁 Struktur

```
vid/
├── downloader.py      ← Script utama
├── run.sh             ← Launcher (gunakan ini!)
├── requirements.txt
├── README.md
├── venv/              ← Virtual environment
└── downloads/         ← Hasil download (dibuat otomatis)
```

---

## ⚠️ Catatan

- Gunakan hanya untuk konten yang **Anda berhak unduh**.
- Jika error `Network is unreachable` → internet tidak tersambung atau situs diblokir ISP → gunakan opsi `-p` (proxy/VPN).
