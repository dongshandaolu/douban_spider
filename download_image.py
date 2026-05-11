import os
from pathlib import Path

import requests

from utils import random_headers, safe_filename


def download_with_resume(url, title, save_dir="images"):
    if not url:
        return ""
    save_dir = Path(save_dir)
    save_dir.mkdir(exist_ok=True)
    path = save_dir / f"{safe_filename(title)}.jpg"
    # 断点续传：已有完整文件则跳过重新下载
    if path.exists() and path.stat().st_size > 0:
        return str(path)
    temp = str(path) + ".part"

    headers = random_headers()
    downloaded = 0
    if os.path.exists(temp):
        downloaded = os.path.getsize(temp)
        headers["Range"] = f"bytes={downloaded}-"

    with requests.get(url, headers=headers, stream=True, timeout=15) as r:
        r.raise_for_status()
        mode = "ab" if downloaded else "wb"
        with open(temp, mode) as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)

    os.replace(temp, path)
    return str(path)
