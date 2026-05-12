"""
豆瓣电影详情（Selenium + 无头）：上映年份、片长、类型、IMDb、热门短评（≥15）、海报本地下载（断点续传）。
现已适配 Microsoft Edge 浏览器 + msedgedriver.exe。

- 结果：`data/movie_selenium_enriched.json`（可 `--out-json`）、`data/movie_comments_nlp.jsonl`（每行一条短评，可 `--out-jsonl`）。
- 海报：`images/` 下按标题安全文件名保存；`download_image.download_with_resume` 支持 .part 与已存在文件跳过。
- 批量默认断点续传：已有输出且短评条数足够则跳过该影片（`--no-resume` 全量重爬）。

数据源默认：`data/movie.json`（由 main_requests 生成）。也可 `--demo-mid` 跑单部。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from db import (
    ensure_movie_exists,
    init_db,
    insert_comment,
    update_douban_top250_selenium_fields,
)
from download_image import download_with_resume
from settings import BASE_DIR, DATA_DIR, IMG_DIR
from utils import get_logger, norm_text, random_delay

logger = get_logger("main_selenium", "logs/main_selenium.log")

# 短评列表：status=P 为短评；sort=vote 为「最有用/热度」排序（便于凑满热门短评）
COMMENTS_HOT_URL = (
    "https://movie.douban.com/subject/{mid}/comments?status=P&sort=vote"
)
COMMENTS_HOT_FALLBACK_URL = (
    "https://movie.douban.com/subject/{mid}/comments?status=P&sort=new_score"
)


def _resolve_edgedriver_path() -> str:
    """驱动路径：环境变量 > 项目根目录 ``msedgedriver.exe`` / ``msedgedriver``。"""
    # 优先使用用户指定的路径
    for env_var in ("SELENIUM_EDGEDRIVER_PATH", "SELENIUM_CHROMEDRIVER_PATH"):
        env = os.environ.get(env_var, "").strip()
        if env and Path(env).is_file():
            return env
    # 自动查找项目根目录下的驱动文件
    for name in ("msedgedriver.exe", "msedgedriver"):
        p = BASE_DIR / name
        if p.is_file():
            return str(p.resolve())
    return ""


def build_driver() -> webdriver.Edge:
    """创建 Edge。

    1. 环境变量 ``SELENIUM_EDGEDRIVER_PATH`` 指向本机驱动（绝对/相对路径均可）。
    2. 否则若项目根目录存在 ``msedgedriver.exe``（Windows）或 ``msedgedriver``（Linux/macOS），自动使用。
    3. 否则交给 Selenium Manager 自动解析（需能访问官方驱动源）。
    """
    opts = EdgeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1400,1200")
    # 压低 Chromium 控制台噪声（GPU/USB 枚举等）；避免中文系统下编码错乱刷屏
    opts.add_argument("--log-level=3")
    opts.add_experimental_option("excludeSwitches", ["enable-logging"])
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0"
    )
    exe = _resolve_edgedriver_path()
    svc = (
        EdgeService(executable_path=exe, log_output=subprocess.DEVNULL)
        if exe
        else EdgeService(log_output=subprocess.DEVNULL)
    )
    drv = webdriver.Edge(service=svc, options=opts)
    drv.set_page_load_timeout(45)
    drv.implicitly_wait(0)
    return drv


def subject_id_from_url(url: str) -> str:
    m = re.search(r"/subject/(\d+)", url or "")
    return m.group(1) if m else ""


def star_class_to_score(class_str: str) -> str:
    if not class_str:
        return ""
    m = re.search(r"allstar(\d{2})", class_str)
    if m:
        return str(int(m.group(1)) / 10)
    return ""


def parse_detail_meta(html: str) -> dict[str, str]:
    """从详情页 HTML 解析：上映年份、片长、类型、IMDb、海报 URL。"""
    soup = BeautifulSoup(html, "lxml")
    out: dict[str, str] = {
        "release_year": "",
        "duration": "",
        "genre": "",
        "imdb_rating_text": "",
        "imdb_score": "",
        "imdb_id": "",
        "poster_url": "",
    }
    h1 = soup.select_one("#content h1")
    if h1:
        spans = h1.select("span")
        if len(spans) >= 2:
            y = norm_text(spans[1].get_text())
            out["release_year"] = y.strip("()（）")

    info = soup.select_one("#info")
    if info:
        text = info.get_text("\n")
        dm = re.search(r"上映日期:\s*([^\n]+)", text)
        if dm:
            ym = re.search(r"(\d{4})", dm.group(1))
            if ym:
                out["release_year"] = out["release_year"] or ym.group(1)
        m = re.search(r"片长:\s*([^\n]+)", text)
        if m:
            out["duration"] = norm_text(m.group(1))
        m = re.search(r"类型:\s*([^\n]+)", text)
        if m:
            out["genre"] = norm_text(m.group(1))

    imdb_a = soup.select_one('#info a[href*="imdb.com/title"]')
    tt = ""
    if imdb_a:
        tt = norm_text(imdb_a.get_text())
        href = imdb_a.get("href") or ""
        if not tt or not tt.startswith("tt"):
            tm = re.search(r"(tt\d+)", href + " " + (tt or ""))
            if tm:
                tt = tm.group(1)

    rating_num = ""
    flat = soup.get_text(" ", strip=True)
    rm = re.search(r"IMDb\s*[：:\s]+([\d.]+)\s*(?:分)?", flat)
    if rm:
        rating_num = rm.group(1)
    if rating_num:
        out["imdb_score"] = rating_num
    if tt:
        out["imdb_id"] = tt
    if rating_num and tt:
        out["imdb_rating_text"] = f"{rating_num} ({tt})"
    elif rating_num:
        out["imdb_rating_text"] = rating_num
    elif tt:
        out["imdb_rating_text"] = tt

    img = soup.select_one("#mainpic img")
    if img and img.get("src"):
        out["poster_url"] = norm_text(img["src"])

    return out


def parse_comments(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    rows: list[dict[str, str]] = []
    for c in soup.select("div.comment-item"):
        commenter = ""
        a = c.select_one("span.comment-info > a")
        if a:
            commenter = norm_text(a.get_text())
        content = norm_text(c.select_one("span.short").get_text()) if c.select_one("span.short") else ""
        time_tag = c.select_one("span.comment-time")
        if time_tag and time_tag.get("title"):
            comment_time = norm_text(time_tag.get("title"))
        else:
            comment_time = norm_text(time_tag.get_text() if time_tag else "")
        star_tag = c.select_one("span.comment-info span[class*='allstar']")
        comment_score = star_class_to_score(" ".join(star_tag.get("class", []))) if star_tag else ""
        if content:
            rows.append(
                {
                    "commenter": commenter,
                    "content": content,
                    "comment_time": comment_time,
                    "comment_score": comment_score,
                }
            )
    return rows


def _comment_key(row: dict[str, Any]) -> tuple[str, str, str]:
    content = row.get("content") or row.get("text") or ""
    return (
        row.get("commenter") or row.get("author") or "",
        row.get("comment_time") or row.get("datetime") or "",
        content[:80],
    )


def shape_comment_nlp(
    subject_id: str,
    seq: int,
    movie_title: str,
    detail_url: str,
    raw: dict[str, Any],
) -> dict[str, Any]:
    """单条短评：同时满足 SQLite 写入与下游 NLP（text / doc_id / 元数据）。"""
    commenter = raw.get("commenter") or raw.get("author") or ""
    content = (raw.get("content") or raw.get("text") or "").strip()
    comment_time = raw.get("comment_time") or raw.get("datetime") or ""
    comment_score = str(raw.get("comment_score") or raw.get("rating") or "")
    doc_id = f"{subject_id}_{seq:03d}"
    return {
        "doc_id": doc_id,
        "subject_id": subject_id,
        "movie_title": movie_title,
        "detail_url": detail_url,
        "author": commenter,
        "rating": comment_score,
        "datetime": comment_time,
        "text": content,
        "commenter": commenter,
        "content": content,
        "comment_time": comment_time,
        "comment_score": comment_score,
    }


def selenium_record_complete(rec: dict[str, Any] | None, comment_limit: int) -> bool:
    if not rec:
        return False
    n = len(rec.get("comments") or [])
    return n >= comment_limit


def write_enriched_and_jsonl(
    ordered: list[dict[str, Any]],
    out_json: Path,
    out_jsonl: Path,
) -> None:
    """写入 enriched JSON + 每行一条短评的 JSONL（便于 pandas / HuggingFace datasets）。"""
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines: list[str] = []
    for movie in ordered:
        mid = movie.get("subject_id") or subject_id_from_url(movie.get("detail_url", ""))
        mtitle = movie.get("title", "")
        durl = movie.get("detail_url", "")
        for c in movie.get("comments") or []:
            lines.append(
                json.dumps(
                    {
                        "doc_id": c.get("doc_id", ""),
                        "text": c.get("text", c.get("content", "")),
                        "movie_title": mtitle,
                        "subject_id": mid,
                        "author": c.get("author", c.get("commenter", "")),
                        "rating": c.get("rating", c.get("comment_score", "")),
                        "datetime": c.get("datetime", c.get("comment_time", "")),
                        "label": None,
                        "meta": {
                            "source": "douban_short_comment",
                            "detail_url": durl,
                            "genre": movie.get("genre", ""),
                            "release_year": movie.get("release_year", ""),
                            "imdb_score": movie.get("imdb_score", ""),
                        },
                    },
                    ensure_ascii=False,
                )
            )
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    out_jsonl.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def expand_hot_comments_on_detail(
    driver: webdriver.Chrome,
    limit: int,
) -> list[dict[str, str]]:
    """在详情页通过「加载更多」展开热门短评（同一 DOM 结构与短评列表页）。"""
    try:
        driver.execute_script(
            "var el=document.querySelector('#comments-section,#hot-comments,.mod-hd+#comments');"
            "if(el) el.scrollIntoView({behavior:'instant',block:'start'});"
        )
        time.sleep(0.6)
    except Exception:
        pass

    collected: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    for _ in range(30):
        html = driver.page_source
        for row in parse_comments(html):
            k = _comment_key(row)
            if k not in seen:
                seen.add(k)
                collected.append(row)
                if len(collected) >= limit:
                    return collected[:limit]

        clicked = False
        for by, sel in (
            (By.PARTIAL_LINK_TEXT, "加载更多"),
            (By.LINK_TEXT, "加载更多"),
            (By.CSS_SELECTOR, "a.comment-more"),
            (By.CSS_SELECTOR, "a[href*='comments'][data-action]"),
        ):
            try:
                btn = driver.find_element(by, sel)
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    clicked = True
                    time.sleep(1.6)
                    break
            except NoSuchElementException:
                continue

        if not clicked:
            break

    return collected[:limit]


def collect_hot_comments(
    driver: webdriver.Chrome,
    movie_id: str,
    movie_title: str,
    detail_url: str,
    limit: int = 15,
) -> list[dict[str, Any]]:
    """短评列表页：按热度（有用）排序 + 翻页，直至凑满 limit 条。"""

    def _open_comments_list(u: str) -> bool:
        driver.get(u)
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.comment-item"))
            )
            return True
        except TimeoutException:
            return False

    primary = COMMENTS_HOT_URL.format(mid=movie_id)
    if not _open_comments_list(primary):
        fb = COMMENTS_HOT_FALLBACK_URL.format(mid=movie_id)
        if not _open_comments_list(fb):
            logger.warning("短评页无评论项: subject=%s", movie_id)
            return []

    collected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    stagnant_rounds = 0

    while len(collected) < limit and stagnant_rounds < 3:
        before = len(collected)
        html = driver.page_source
        for row in parse_comments(html):
            k = _comment_key(row)
            if k in seen:
                continue
            seen.add(k)
            row["movie_title"] = movie_title
            row["detail_url"] = detail_url
            collected.append(row)
            if len(collected) >= limit:
                break

        if len(collected) >= limit:
            break

        if len(collected) == before:
            stagnant_rounds += 1
        else:
            stagnant_rounds = 0

        try:
            more = driver.find_element(By.CSS_SELECTOR, "a.next")
            cls = more.get_attribute("class") or ""
            if more.is_displayed() and "disabled" not in cls:
                driver.execute_script("arguments[0].click();", more)
                time.sleep(1.8)
            else:
                break
        except NoSuchElementException:
            break

    return collected[:limit]


def load_jobs_from_json(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    jobs: list[dict[str, str]] = []
    for row in raw:
        title = row.get("电影名") or row.get("title") or ""
        href = row.get("详情链接") or row.get("detail_url") or ""
        if title and href and "douban.com/subject/" in href:
            jobs.append({"title": title, "detail_url": href})
    return jobs


def crawl_movie_detail(
    driver: webdriver.Chrome,
    movie_title: str,
    detail_url: str,
    *,
    comment_limit: int = 15,
    download_poster: bool = True,
) -> dict[str, Any]:
    """打开详情页解析元数据；下载海报；再抓取热门短评。"""
    init_db()
    mid = subject_id_from_url(detail_url)
    if not mid:
        logger.error("无法解析 subject id: %s", detail_url)
        return {}

    ensure_movie_exists(movie_title, detail_url)

    driver.get(detail_url)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#info"))
        )
    except TimeoutException:
        logger.warning("详情页加载超时: %s", detail_url)

    random_delay()
    meta = parse_detail_meta(driver.page_source)

    poster_local = ""
    if download_poster and meta.get("poster_url"):
        try:
            poster_local = download_with_resume(meta["poster_url"], movie_title, str(IMG_DIR))
        except Exception as e:
            logger.warning("海报下载失败 %s: %s", movie_title, e)

    update_douban_top250_selenium_fields(
        movie_title,
        duration=meta.get("duration", ""),
        genre=meta.get("genre", ""),
        imdb_ref=meta.get("imdb_rating_text", ""),
        poster_local=poster_local or "",
    )

    detail_comments = expand_hot_comments_on_detail(driver, comment_limit)
    merged: list[dict[str, Any]] = []
    seen_k: set[tuple[str, str, str]] = set()
    for row in detail_comments:
        k = _comment_key(row)
        if k in seen_k:
            continue
        seen_k.add(k)
        merged.append(dict(row))

    need = comment_limit - len(merged)
    if need > 0:
        rest = collect_hot_comments(
            driver, mid, movie_title, detail_url, limit=comment_limit
        )
        for row in rest:
            k = _comment_key(row)
            if k in seen_k:
                continue
            seen_k.add(k)
            slim = {kk: vv for kk, vv in row.items() if kk not in ("movie_title", "detail_url")}
            merged.append(slim)
            if len(merged) >= comment_limit:
                break

    merged_raw = merged[:comment_limit]
    comments_out = [
        shape_comment_nlp(mid, i + 1, movie_title, detail_url, raw)
        for i, raw in enumerate(merged_raw)
    ]
    for one in comments_out:
        try:
            insert_comment(one)
        except Exception as e:
            logger.warning("写入短评失败 %s: %s", movie_title, e)

    return {
        "title": movie_title,
        "subject_id": mid,
        "detail_url": detail_url,
        "release_year": meta.get("release_year", ""),
        "duration": meta.get("duration", ""),
        "genre": meta.get("genre", ""),
        "imdb_rating_text": meta.get("imdb_rating_text", ""),
        "imdb_score": meta.get("imdb_score", ""),
        "imdb_id": meta.get("imdb_id", ""),
        "poster_url": meta.get("poster_url", ""),
        "poster_local": poster_local,
        "comments": comments_out,
    }


def run_batch_from_json(
    json_path: Path | None = None,
    *,
    comment_limit: int = 15,
    out_json: Path | None = None,
    out_jsonl: Path | None = None,
    resume: bool = True,
) -> list[dict[str, Any]]:
    path = json_path or (DATA_DIR / "movie.json")
    out_path = out_json or (DATA_DIR / "movie_selenium_enriched.json")
    jsonl_path = out_jsonl or (DATA_DIR / "movie_comments_nlp.jsonl")
    jobs = load_jobs_from_json(path)
    if not jobs:
        logger.error("未找到影片列表: %s", path)
        return []

    by_title: dict[str, dict[str, Any]] = {}
    if resume and out_path.exists():
        try:
            prev = json.loads(out_path.read_text(encoding="utf-8"))
            for rec in prev:
                t = rec.get("title")
                if t:
                    by_title[str(t)] = rec
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("断点续读失败 %s: %s", out_path, e)

    driver = build_driver()
    try:
        for i, job in enumerate(jobs):
            t = job["title"]
            if resume and selenium_record_complete(by_title.get(t), comment_limit):
                logger.info("跳过已完成 [%s/%s] %s", i + 1, len(jobs), t)
                continue
            logger.info("[%s/%s] %s", i + 1, len(jobs), t)
            random_delay()
            try:
                r = crawl_movie_detail(
                    driver,
                    job["title"],
                    job["detail_url"],
                    comment_limit=comment_limit,
                )
                if r:
                    by_title[job["title"]] = r
                    ordered = [by_title[j["title"]] for j in jobs if j["title"] in by_title]
                    write_enriched_and_jsonl(ordered, out_path, jsonl_path)
            except Exception as e:
                logger.exception("抓取失败 %s: %s", job["title"], e)
    finally:
        driver.quit()

    ordered = [by_title[j["title"]] for j in jobs if j["title"] in by_title]
    write_enriched_and_jsonl(ordered, out_path, jsonl_path)
    logger.info("已写入 %s 与 %s", out_path, jsonl_path)
    return ordered


def crawl_comments(
    movie_title: str,
    movie_id: str,
    detail_url: str,
    limit: int = 15,
) -> list[dict[str, Any]]:
    """兼容旧接口：仅打开短评列表页（热门排序）并翻页，写入 comments 表。"""
    init_db()
    ensure_movie_exists(movie_title, detail_url)
    driver = build_driver()
    try:
        rows = collect_hot_comments(
            driver, movie_id, movie_title, detail_url, limit=limit
        )
        for row in rows:
            try:
                insert_comment(row)
            except Exception as e:
                logger.warning("写入短评失败 %s: %s", movie_title, e)
        return rows
    finally:
        driver.quit()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="豆瓣详情 Selenium 抓取")
    parser.add_argument("--demo-mid", default="", help="仅跑一部，subject id，例如 1292052")
    parser.add_argument("--json", type=Path, default="data/movie.json", help="影片列表 JSON，默认 data/movie.json")
    parser.add_argument("--comments", type=int, default=15, help="热门短评条数")
    parser.add_argument(
        "--out-json",
        type=Path,
        default=None,
        help="详情+短评输出路径，默认 data/movie_selenium_enriched.json",
    )
    parser.add_argument(
        "--out-jsonl",
        type=Path,
        default=None,
        help="NLP 用 JSONL（每行一条短评），默认 data/movie_comments_nlp.jsonl",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="忽略已有输出，全量重爬（仍会覆盖写入 out-json / out-jsonl）",
    )
    args = parser.parse_args()

    if args.demo_mid:
        title = f"subject_{args.demo_mid}"
        url = f"https://movie.douban.com/subject/{args.demo_mid}/"
        d = build_driver()
        try:
            r = crawl_movie_detail(d, title, url, comment_limit=args.comments)
            print(json.dumps(r, ensure_ascii=False, indent=2))
        finally:
            d.quit()
    else:
        run_batch_from_json(
            args.json,
            comment_limit=args.comments,
            out_json=args.out_json,
            out_jsonl=args.out_jsonl,
            resume=not args.no_resume,
        )
