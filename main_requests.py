import os
import re
import json
import csv
import time
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
from pathlib import Path

from settings import DATA_DIR, IMG_DIR, TIMEOUT, RETRY
from utils import (
    get_logger, random_headers, random_delay, pick_proxy,
    norm_text, safe_filename, join_url, robots_allowed )
from db import init_db, upsert_movie, insert_comment

BASE_URL = "https://movie.douban.com/top250"

logger = get_logger("requests_spider")


def fetch(url):
    for i in range(RETRY):
        try:
            random_delay()
            resp = requests.get(
                url,
                headers=random_headers(),
                proxies=pick_proxy(),
                timeout=TIMEOUT
            )
            if resp.status_code == 200:
                return resp.text
            logger.warning(f"status={resp.status_code}, retry={i+1}, url={url}")
        except Exception as e:
            logger.warning(f"fetch error retry={i+1}, url={url}, err={e}")
    return None


def parse_list(html):
    soup = BeautifulSoup(html, "lxml")
    items = []
    for li in soup.select("ol.grid_view > li"):
        rank = norm_text(li.select_one("em").get_text())
        title_cn = norm_text(li.select_one("span.title").get_text())
        title_all = [norm_text(x.get_text()) for x in li.select("span.title")]
        title_en = title_all[1] if len(title_all) > 1 else ""
        detail_url = li.select_one("a")["href"]

        score = norm_text(li.select_one("span.rating_num").get_text())
        star_spans = li.select("div.star span")
        if star_spans:
            vote_text = star_spans[-1].get_text()
        else:
            vote_text = ""
        vote_count = int(re.sub(r"\D", "", vote_text) or 0)

        director = norm_text(li.select_one("div.bd p").get_text(" ", strip=True))
        intro_tag = li.select_one("span.inq")
        intro = norm_text(intro_tag.get_text()) if intro_tag else ""

        items.append({
            "rank_num": int(rank),
            "title": title_cn,
            "title_en": title_en,
            "score": float(score),
            "vote_count": vote_count,
            "director": director,
            "intro": intro,
            "detail_url": detail_url,
        })
    return items


def parse_detail(html):
    soup = BeautifulSoup(html, "lxml")
    info_text = soup.select_one("div#info").get_text("\n", strip=True) if soup.select_one("div#info") else ""
    year = re.search(r"(\d{4})", soup.select_one("span.year").get_text() if soup.select_one("span.year") else "")
    year = year.group(1) if year else ""

    duration = ""
    genre = ""
    imdb_score = ""

    m = re.search(r"片长:\s*([^\n]+)", info_text)
    if m:
        duration = norm_text(m.group(1))

    m = re.search(r"类型:\s*([^\n]+)", info_text)
    if m:
        genre = norm_text(m.group(1))

    m = re.search(r"IMDb:\s*([0-9.]+)", info_text)
    if m:
        imdb_score = m.group(1)

    poster = ""
    img = soup.select_one("a.nbgnbg img")
    if img and img.get("src"):
        poster = img["src"]

    return {
        "year": year,
        "duration": duration,
        "genre": genre,
        "imdb_score": imdb_score,
        "poster_url": poster,
    }


def download_image(url, title):
    if not url:
        return ""
    fname = safe_filename(title) + ".jpg"
    path = IMG_DIR / fname
    if path.exists() and path.stat().st_size > 0:
        return str(path)

    try:
        r = requests.get(url, headers=random_headers(), stream=True, timeout=TIMEOUT)
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
        return str(path)
    except Exception as e:
        logger.warning(f"image download failed: {title}, {e}")
        return ""


def main():
    init_db()
    movies = []
    for page in tqdm(range(10), desc="list pages"):
        url = f"{BASE_URL}?start={page*25}&filter="
        if not robots_allowed(BASE_URL, url):
            logger.warning(f"robots denied: {url}")
            continue

        html = fetch(url)
        if not html:
            continue

        for movie in parse_list(html):
            detail_html = fetch(movie["detail_url"])
            if detail_html:
                extra = parse_detail(detail_html)
                movie.update(extra)
                movie["poster_path"] = download_image(extra.get("poster_url", ""), movie["title"])
            else:
                movie["poster_path"] = ""

            upsert_movie(movie)
            movies.append(movie)

    DATA_DIR.mkdir(exist_ok=True)
    with open(DATA_DIR / "movies.json", "w", encoding="utf-8") as f:
        json.dump(movies, f, ensure_ascii=False, indent=2)

    with open(DATA_DIR / "movies.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=movies[0].keys() if movies else [])
        writer.writeheader()
        writer.writerows(movies)


if __name__ == "__main__":
    main()

