# Movie Spider 项目

一个覆盖课程要求的电影数据采集与分析项目，包含：

- 列表页 + 详情页抓取（`requests` + `BeautifulSoup`）
- Selenium 动态短评加载
- 图片下载（含断点续传实现）
- SQLite 数据库存储
- Scrapy 重构
- 数据清洗、统计分析与可视化
- 日志、重试、随机 UA、延时、`robots.txt` 检查
- 三人分工模板

## 1. 环境准备

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. 运行顺序

```bash
python main_requests.py
python main_selenium.py
cd scrapy_project
scrapy crawl movie
cd ..
python analysis/analyze.py
```

## 3. 产物目录

- `data/movies.csv`
- `data/movies.json`
- `data/movie.db`
- `images/*.jpg`
- `output/*.png`
- `logs/spider.log`

## 4. 团队分工（可直接用于报告）

- 成员 A：`requests` 列表页/详情页爬取、Selenium 动态短评、图片下载、反爬策略
- 成员 B：Scrapy 重构、数据库 Pipeline、数据清洗、日志与异常处理
- 成员 C：统计分析、可视化、情感分析、报告整合、Git 协作、PPT 制作

## 5. 注意事项

- 目标站点选择器可能变化，请按实时 HTML 微调。
- 遵守目标站点协议，避免高并发请求。
- 如 Selenium 报驱动问题，可改用 `webdriver-manager` 自动安装驱动。
Movie Spider Project

快速启动：

1) 创建虚拟环境并安装依赖：

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
import re
2) 运行 requests 版爬虫（列表 + 详情 + 图片 + SQLite/CSV/JSON）：

python main_requests.py

3) 运行 Selenium 版（动态短评，需 ChromeDriver）：

python main_selenium.py

4) 运行 Scrapy 重构：

cd scrapy_project
scrapy crawl movie

5) 数据清洗与分析：

python analysis\analyze.py

输出：
- data/movies.csv
- data/comments.csv
- data/movie.db
- data/json/*.json
- images/*.jpg
- output/*.png
- logs/spider.log

团队分工（示例）:
- 成员 A：requests 列表页/详情页爬取、Selenium 动态短评、图片下载、反爬策略。
- 成员 B：Scrapy 重构、数据库 Pipeline、数据清洗、日志与异常处理。
- 成员 C：统计分析、可视化、情感分析、报告整合、PPT 制作。

说明：页面选择器需根据目标站点 HTML 微调，遵守 robots.txt 与目标站点爬虫策略。
import scrapy
from bs4 import BeautifulSoup
from moviebot.items import MovieItem

class MovieSpider(scrapy.Spider):
    name = "movie"
    allowed_domains = ["movie.douban.com"]
    start_urls = [f"https://movie.douban.com/top250?start={i*25}&filter=" for i in range(10)]

    def parse(self, response):
        soup = BeautifulSoup(response.text, "lxml")
        for li in soup.select("ol.grid_view > li"):
            item = MovieItem()
            item["rank_num"] = int(li.select_one("em").get_text(strip=True))
            item["title"] = li.select_one("span.title").get_text(strip=True)
            titles = [x.get_text(strip=True) for x in li.select("span.title")]
            item["title_en"] = titles[1] if len(titles) > 1 else ""
            item["score"] = float(li.select_one("span.rating_num").get_text(strip=True))
            vote_text = li.select("div.star span")[3].get_text(strip=True)
            item["vote_count"] = int(re.sub(r"\D", "", vote_text) or 0)
            item["director"] = li.select_one("div.bd p").get_text(" ", strip=True)
            intro = li.select_one("span.inq")
            item["intro"] = intro.get_text(strip=True) if intro else ""
            item["detail_url"] = li.select_one("a")["href"]
            yield scrapy.Request(item["detail_url"], callback=self.parse_detail, meta={"item": item})

    def parse_detail(self, response):
        item = response.meta["item"]
        soup = BeautifulSoup(response.text, "lxml")
        info = soup.select_one("div#info").get_text("\n", strip=True) if soup.select_one("div#info") else ""

        item["year"] = re.search(r"(\d{4})", soup.get_text()).group(1) if re.search(r"(\d{4})", soup.get_text()) else ""
        m = re.search(r"片长:\s*([^\n]+)", info)
        item["duration"] = m.group(1).strip() if m else ""
        m = re.search(r"类型:\s*([^\n]+)", info)
        item["genre"] = m.group(1).strip() if m else ""
        m = re.search(r"IMDb:\s*([0-9.]+)", info)
        item["imdb_score"] = m.group(1) if m else ""

        img = soup.select_one("a.nbgnbg img")
        item["poster_path"] = img["src"] if img and img.get("src") else ""
        yield item
BOT_NAME = "moviebot"
SPIDER_MODULES = ["moviebot.spiders"]
NEWSPIDER_MODULE = "moviebot.spiders"

ROBOTSTXT_OBEY = True
CONCURRENT_REQUESTS = 8
DOWNLOAD_DELAY = 1
RETRY_TIMES = 3
LOG_LEVEL = "INFO"

UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]

PROXY_LIST = []

ITEM_PIPELINES = {
    "moviebot.pipelines.SqlitePipeline": 300,
}

DOWNLOADER_MIDDLEWARES = {
    "moviebot.middlewares.RandomUserAgentMiddleware": 543,
    "moviebot.middlewares.SimpleProxyMiddleware": 544,
}
import sqlite3
from pathlib import Path

class SqlitePipeline:
    def open_spider(self, spider):
        self.db_path = Path("data/movie.db")
        self.db_path.parent.mkdir(exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.cur = self.conn.cursor()

        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            title TEXT PRIMARY KEY,
            title_en TEXT, rank_num INTEGER, score REAL, vote_count INTEGER,
            director TEXT, intro TEXT, detail_url TEXT, year TEXT,
            duration TEXT, genre TEXT, imdb_score TEXT, poster_path TEXT
        )""")

        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            movie_title TEXT,
            commenter TEXT,
            comment_score TEXT,
            content TEXT,
            comment_time TEXT,
            detail_url TEXT,
            FOREIGN KEY(movie_title) REFERENCES movies(title)
        )""")
        self.conn.commit()

    def process_item(self, item, spider):
        if item.get("commenter") is not None:
            self.cur.execute("""
            INSERT INTO comments(movie_title, commenter, comment_score, content, comment_time, detail_url)
            VALUES(?,?,?,?,?,?)
            """, (
                item.get("movie_title"), item.get("commenter"), item.get("comment_score"),
                item.get("content"), item.get("comment_time"), item.get("detail_url")
            ))
        else:
            self.cur.execute("""
            INSERT OR REPLACE INTO movies(title, title_en, rank_num, score, vote_count, director, intro, detail_url, year, duration, genre, imdb_score, poster_path)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                item.get("title"), item.get("title_en"), item.get("rank_num"), item.get("score"),
                item.get("vote_count"), item.get("director"), item.get("intro"), item.get("detail_url"),
                item.get("year"), item.get("duration"), item.get("genre"), item.get("imdb_score"),
                item.get("poster_path"),
            ))
        self.conn.commit()
        return item

    def close_spider(self, spider):
        self.conn.close()
import random

class RandomUserAgentMiddleware:
    def __init__(self, agents):
        self.agents = agents

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings.get("UA_LIST", []))

    def process_request(self, request, spider):
        if self.agents:
            request.headers["User-Agent"] = random.choice(self.agents)

class SimpleProxyMiddleware:
    def __init__(self, proxies):
        self.proxies = proxies

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings.get("PROXY_LIST", []))

    def process_request(self, request, spider):
        if self.proxies:
            request.meta["proxy"] = random.choice(self.proxies)
import scrapy

class MovieItem(scrapy.Item):
    title = scrapy.Field()
    title_en = scrapy.Field()
    rank_num = scrapy.Field()
    score = scrapy.Field()
    vote_count = scrapy.Field()
    director = scrapy.Field()
    intro = scrapy.Field()
    detail_url = scrapy.Field()
    year = scrapy.Field()
    duration = scrapy.Field()
    genre = scrapy.Field()
    imdb_score = scrapy.Field()
    poster_path = scrapy.Field()

class CommentItem(scrapy.Item):
    movie_title = scrapy.Field()
    commenter = scrapy.Field()
    comment_score = scrapy.Field()
    content = scrapy.Field()
    comment_time = scrapy.Field()
    detail_url = scrapy.Field()
[settings]
default = moviebot.settings
import re
import math
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

try:
    import jieba
    from snownlp import SnowNLP
except Exception:
    jieba = None
    SnowNLP = None

DATA = Path("data/movies.csv")
OUT = Path("output")
OUT.mkdir(exist_ok=True)


def clean_df(df):
    df = df.drop_duplicates(subset=["title"]).copy()
    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    df["vote_count"] = pd.to_numeric(df["vote_count"], errors="coerce").fillna(0).astype(int)
    df["rank_num"] = pd.to_numeric(df["rank_num"], errors="coerce").astype("Int64")
    df["year"] = df["year"].astype(str).str.extract(r"(\d{4})", expand=False)
    return df


def split_genre(df):
    s = df["genre"].fillna("").astype(str).str.split(r"[\/\\,、; ]+")
    return df.assign(genre_item=s).explode("genre_item")


def plot_basic(df):
    plt.figure()
    df["score"].dropna().hist(bins=15)
    plt.title("评分分布")
    plt.xlabel("score")
    plt.ylabel("count")
    plt.tight_layout()
    plt.savefig(OUT / "score_hist.png", dpi=300)
    plt.close()

    plt.figure()
    top10 = df.nlargest(10, "score")[["title", "score"]].sort_values("score")
    plt.barh(top10["title"], top10["score"])
    plt.title("高分电影Top10")
    plt.tight_layout()
    plt.savefig(OUT / "top10.png", dpi=300)
    plt.close()

    plt.figure()
    plt.scatter(df["vote_count"], df["score"])
    plt.xlabel("vote_count")
    plt.ylabel("score")
    plt.title("评分与评价人数关系")
    plt.tight_layout()
    plt.savefig(OUT / "scatter_votes_score.png", dpi=300)
    plt.close()


def sentiment_stats(df):
    if "intro" not in df.columns:
        return
    texts = df["intro"].dropna().astype(str).tolist()
    if not texts or SnowNLP is None:
        return
    scores = [SnowNLP(t).sentiments for t in texts if len(t.strip()) > 1]
    if not scores:
        return
    pos = sum(s >= 0.6 for s in scores)
    neu = sum(0.4 <= s < 0.6 for s in scores)
    neg = sum(s < 0.4 for s in scores)
    print("情感统计:", {"正面": pos, "中性": neu, "负面": neg})


def main():
    df = pd.read_csv(DATA)
    df = clean_df(df)
    df.to_csv(OUT / "clean_movies.csv", index=False, encoding="utf-8-sig")

    print("总数:", len(df))
    print("Top10:")
    print(df.nlargest(10, "score")[["title", "score", "vote_count"]])

    genre_df = split_genre(df)
    genre_count = genre_df["genre_item"].value_counts().head(10)
    plt.figure()
    genre_count.plot(kind="bar")
    plt.title("类型分布Top10")
    plt.tight_layout()
    plt.savefig(OUT / "genre_top10.png", dpi=300)
    plt.close()

    corr = df[["score", "vote_count"]].corr().iloc[0, 1]
    print("评分-评价人数相关系数:", round(float(corr), 4))

    plot_basic(df)
    sentiment_stats(df)


if __name__ == "__main__":
    main()
from pathlib import Path
import os
import requests
from utils import random_headers, safe_filename


def download_with_resume(url, title, save_dir="images"):
    if not url:
        return ""
    save_dir = Path(save_dir)
    save_dir.mkdir(exist_ok=True)
    path = save_dir / f"{safe_filename(title)}.jpg"
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
import re
import time
from tqdm import tqdm
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from utils import norm_text, safe_filename
from db import init_db, insert_comment

COMMENT_URL = "https://movie.douban.com/subject/{mid}/comments?status=P"


def build_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1400,1200")
    return webdriver.Chrome(options=opts)


def parse_comments(html):
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for c in soup.select("div.comment-item"):
        commenter = norm_text(c.select_one("a").get_text()) if c.select_one("a") else ""
        content = norm_text(c.select_one("span.short").get_text()) if c.select_one("span.short") else ""
        time_tag = c.select_one("span.comment-time")
        comment_time = norm_text(time_tag.get("title")) if time_tag and time_tag.get("title") else norm_text(time_tag.get_text() if time_tag else "")
        star = ""
        star_tag = c.select_one("span.comment-info span[class*='allstar']")
        if star_tag:
            star = " ".join(star_tag.get("class", []))
        rows.append({
            "commenter": commenter,
            "content": content,
            "comment_time": comment_time,
            "comment_score": star,
        })
    return rows


def crawl_comments(movie_title, movie_id, detail_url, limit=15):
    init_db()
    driver = build_driver()
    try:
        url = COMMENT_URL.format(mid=movie_id)
        driver.get(url)

        # 等待评论区出现
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.comment-item"))
        )

        collected = []
        last_count = 0

        while len(collected) < limit:
            html = driver.page_source
            rows = parse_comments(html)
            for row in rows:
                row["movie_title"] = movie_title
                row["detail_url"] = detail_url
                if row["content"] and row not in collected:
                    collected.append(row)
                    insert_comment(row)
                if len(collected) >= limit:
                    break

            # 尝试点击“加载更多”
            try:
                more = driver.find_element(By.CSS_SELECTOR, "a.next")
                if more.is_displayed():
                    driver.execute_script("arguments[0].click();", more)
                    time.sleep(1.5)
                else:
                    break
            except Exception:
                break

            if len(collected) == last_count:
                break
            last_count = len(collected)

        return collected[:limit]
    finally:
        driver.quit()
requests
beautifulsoup4
lxml
pandas
matplotlib
seaborn
tqdm
selenium
webdriver-manager
scrapy
pymysql
pillow
jieba
snownlp

