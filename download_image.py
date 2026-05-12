import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from settings import DOUBAN_COOKIE_ENV, RETRY, TIMEOUT
from utils import random_headers, safe_filename


def _poster_suffix_from_url(url: str) -> str:
    if not url:
        return ".jpg"
    u = url.lower().split("?")[0]
    for ext in (".webp", ".jpg", ".jpeg", ".png", ".gif"):
        if u.endswith(ext):
            return ext
    m = re.search(r"\.(webp|jpe?g|png|gif)(?:$|[?#])", u)
    return f".{m.group(1)}" if m else ".jpg"


def _safe_unlink(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _poster_request_headers(url: str) -> dict[str, str]:
    """图床反爬：补 Referer / Accept；可选环境变量 DOUBAN_COOKIE。"""
    headers = dict(random_headers())
    host = (urlparse(url).hostname or "").lower()
    if "douban" in host:
        headers["Referer"] = "https://movie.douban.com/"
        headers["Accept"] = (
            "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
        )
        headers["Accept-Language"] = "zh-CN,zh;q=0.9,en;q=0.8"
    else:
        headers.setdefault("Accept", "*/*")
    cookie = os.environ.get(DOUBAN_COOKIE_ENV, "").strip()
    if cookie:
        headers["Cookie"] = cookie
    return headers


def download_with_resume(url, title, save_dir="images"):
    if not url:
        return ""
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    suffix = _poster_suffix_from_url(url)
    path = save_dir / f"{safe_filename(title)}{suffix}"
    if path.exists() and path.stat().st_size > 0:
        return str(path)
    temp = str(path) + ".part"

    backoff = 0.75
    last_err: Exception | None = None

    for attempt in range(RETRY):
        headers = _poster_request_headers(url)
        downloaded = 0
        if os.path.exists(temp):
            sz = os.path.getsize(temp)
            if sz > 0:
                downloaded = sz
                headers["Range"] = f"bytes={downloaded}-"

        try:
            with requests.get(
                url, headers=headers, stream=True, timeout=TIMEOUT
            ) as r:
                if r.status_code == 416:
                    _safe_unlink(temp)
                    last_err = None
                    continue
                if r.status_code in (401, 403, 418, 429):
                    last_err = requests.HTTPError(
                        f"{r.status_code} Client Error for url: {url}", response=r
                    )
                    time.sleep(backoff * (attempt + 1))
                    continue
                r.raise_for_status()

                append = downloaded > 0 and r.status_code == 206
                mode = "ab" if append else "wb"
                with open(temp, mode) as f:
                    for chunk in r.iter_content(8192):
                        if chunk:
                            f.write(chunk)
        except requests.RequestException as e:
            last_err = e
            time.sleep(backoff * (attempt + 1))
            continue

        if os.path.exists(temp) and os.path.getsize(temp) > 0:
            os.replace(temp, path)
            return str(path)
        last_err = OSError("下载完成后临时文件为空")

    if last_err:
        raise last_err
    raise requests.RequestException(f"海报下载失败（已重试 {RETRY} 次）: {url}")
