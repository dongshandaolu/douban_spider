import logging
import os
import re
import time
import random
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

from settings import HEADERS_POOL, PROXIES, TIMEOUT, RETRY, DELAY_RANGE


def get_logger(name="spider", log_file="logs/spider.log"):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(formatter)
    sh = logging.StreamHandler()
    sh.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def random_headers():
    return {"User-Agent": random.choice(HEADERS_POOL)}


def random_delay():
    time.sleep(random.uniform(*DELAY_RANGE))


def pick_proxy():
    if not PROXIES:
        return None
    p = random.choice(PROXIES)
    return {"http": p, "https": p}


def norm_text(s):
    return re.sub(r"\s+", " ", s).strip() if s else ""


def safe_filename(name):
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    return name[:120].strip()


def join_url(base, href):
    return urljoin(base, href)


def robots_allowed(base_url, target_url, ua="*"):
    rp = RobotFileParser()
    rp.set_url(urljoin(base_url, "/robots.txt"))
    try:
        rp.read()
        return rp.can_fetch(ua, target_url)
    except Exception:
        return True

