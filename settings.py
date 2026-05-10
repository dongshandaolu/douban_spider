from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
IMG_DIR = BASE_DIR / "images"
LOG_DIR = BASE_DIR / "logs"
OUT_DIR = BASE_DIR / "output"

for p in [DATA_DIR, IMG_DIR, LOG_DIR, OUT_DIR]:
    p.mkdir(exist_ok=True)

HEADERS_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

PROXIES = []

TIMEOUT = 12
RETRY = 3
DELAY_RANGE = (1, 3)
