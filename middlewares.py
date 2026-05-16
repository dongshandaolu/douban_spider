import os
import random
from urllib.parse import urlparse

from moviebot.douban_defaults import DOUBAN_COOKIES, DOUBAN_HEADERS


def _merge_cookies_from_env(base: dict) -> dict:
    """与 main_requests._merge_cookies_from_env 行为一致。"""
    raw = os.environ.get("DOUBAN_COOKIE", "").strip()
    if not raw:
        return dict(base)
    extra = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            extra[k.strip()] = v.strip()
    return {**base, **extra}


def _cookie_header(cookies: dict) -> str:
    parts = []
    for k, v in cookies.items():
        parts.append(f"{k}={v}")
    return "; ".join(parts)


class RandomUserAgentMiddleware:
    """随机 User-Agent（与 settings.UA_LIST 配合）。"""

    def __init__(self, ua_list):
        self.ua_list = ua_list or []

    @classmethod
    def from_crawler(cls, crawler):
        ua = crawler.settings.get("UA_LIST") or []
        if isinstance(ua, str):
            ua = [ua]
        return cls(ua)

    def process_request(self, request, spider):
        if self.ua_list:
            request.headers[b"User-Agent"] = random.choice(self.ua_list).encode()


class DoubanHeadersMiddleware:
    """Downloader Middleware：对齐 requests 版默认头、Referer、Cookie（含环境变量合并）。"""

    def process_request(self, request, spider):
        host = urlparse(request.url).hostname or ""
        if "douban.com" not in host:
            return None
        for key, val in DOUBAN_HEADERS.items():
            bkey = key.encode() if isinstance(key, str) else key
            if bkey.lower() == b"user-agent" and request.headers.get(b"User-Agent"):
                continue
            request.headers.setdefault(
                key.encode() if isinstance(key, str) else key,
                val.encode() if isinstance(val, str) else val,
            )
        merged = _merge_cookies_from_env(DOUBAN_COOKIES)
        request.headers[b"Cookie"] = _cookie_header(merged).encode()
        return None


class SimpleProxyMiddleware:
    """可选 HTTP(S) 代理，与 settings.PROXY_LIST 配合。"""

    def __init__(self, proxy_list):
        self.proxy_list = proxy_list or []

    @classmethod
    def from_crawler(cls, crawler):
        pl = crawler.settings.get("PROXY_LIST") or []
        if isinstance(pl, str):
            pl = [pl]
        return cls(pl)

    def process_request(self, request, spider):
        if not self.proxy_list:
            return None
        proxy = random.choice(self.proxy_list)
        request.meta["proxy"] = proxy
        return None
