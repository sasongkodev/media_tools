import urllib.parse
import urllib.request
url = "https://www.liveomek.com/video/remaja-hijab-buka-kancing-baju-omek-bikin-halu.html"
# Try Google Web Cache
cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"
try:
    req = urllib.request.Request(cache_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
    resp = urllib.request.urlopen(req, timeout=10).read().decode()
    print("Found video" if "video" in resp.lower() else "Not found")
except Exception as e:
    print("Failed")
