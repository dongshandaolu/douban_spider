import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd

from moviebot.items import DoubanTop250Item

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from db import init_db, save_douban_top250_batch  # noqa: E402
from settings import DATA_DIR  # noqa: E402


class DoubanTop250Pipeline:
    """与 main_requests._persist_outputs 对齐：SQLite douban_top250 + movie.csv + movie.json。"""

    def open_spider(self, spider):
        self.rows: list[dict] = []

    def process_item(self, item, spider):
        if not isinstance(item, DoubanTop250Item):
            return item
        self.rows.append(dict(item))
        return item

    def close_spider(self, spider):
        if not self.rows:
            return
        init_db()
        save_douban_top250_batch(self.rows, replace_all=True)

        columns = [
            "电影名",
            "年份",
            "导演",
            "编剧",
            "主演",
            "地区",
            "剧情",
            "语言",
            "又名",
            "评分",
            "剧情介绍",
            "评论数",
            "海报地址",
        ]
        table_rows = []
        for r in self.rows:
            try:
                actors_list = json.loads(r["actors"]) if r.get("actors") else []
            except json.JSONDecodeError:
                actors_list = []
            actors_cell = " / ".join(actors_list) if isinstance(actors_list, list) else str(r.get("actors", ""))
            table_rows.append(
                [
                    r.get("title", ""),
                    r.get("year", ""),
                    r.get("director", ""),
                    r.get("writer", ""),
                    actors_cell,
                    r.get("area", ""),
                    r.get("plot", ""),
                    r.get("language", ""),
                    r.get("alias", ""),
                    r.get("score", ""),
                    r.get("synopsis", ""),
                    r.get("comment_number", ""),
                    r.get("image_url", ""),
                ]
            )
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        csv_path = DATA_DIR / "movie.csv"
        pd.DataFrame(table_rows, columns=columns).to_csv(csv_path, index=False, encoding="utf-8-sig")
        json_path = DATA_DIR / "movie.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.rows, f, ensure_ascii=False, indent=2)
        spider.logger.info("DoubanTop250Pipeline: 已写入 SQLite、%s、%s", csv_path, json_path)


class SqlitePipeline:
    """原列表爬虫写入 movies / comments 表；跳过 DoubanTop250Item（由 DoubanTop250Pipeline 处理）。"""

    def open_spider(self, spider):
        self.db_path = _ROOT / "data" / "movie.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.cur = self.conn.cursor()

        self.cur.execute(
            """
        CREATE TABLE IF NOT EXISTS movies (
            title TEXT PRIMARY KEY,
            title_en TEXT, rank_num INTEGER, score REAL, vote_count INTEGER,
            director TEXT, intro TEXT, detail_url TEXT, year TEXT,
            duration TEXT, genre TEXT, imdb_score TEXT, poster_path TEXT
        )"""
        )
        self.cur.execute(
            """
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            movie_title TEXT,
            commenter TEXT,
            comment_score TEXT,
            content TEXT,
            comment_time TEXT,
            detail_url TEXT,
            FOREIGN KEY(movie_title) REFERENCES movies(title)
        )"""
        )
        self.conn.commit()

    def process_item(self, item, spider):
        if isinstance(item, DoubanTop250Item):
            return item
        if item.get("commenter") is not None:
            self.cur.execute(
                """
            INSERT INTO comments(movie_title, commenter, comment_score, content, comment_time, detail_url)
            VALUES(?,?,?,?,?,?)
            """,
                (
                    item.get("movie_title"),
                    item.get("commenter"),
                    item.get("comment_score"),
                    item.get("content"),
                    item.get("comment_time"),
                    item.get("detail_url"),
                ),
            )
        else:
            self.cur.execute(
                """
            INSERT OR REPLACE INTO movies(title, title_en, rank_num, score, vote_count, director, intro, detail_url, year, duration, genre, imdb_score, poster_path)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
                (
                    item.get("title"),
                    item.get("title_en"),
                    item.get("rank_num"),
                    item.get("score"),
                    item.get("vote_count"),
                    item.get("director"),
                    item.get("intro"),
                    item.get("detail_url"),
                    item.get("year"),
                    item.get("duration"),
                    item.get("genre"),
                    item.get("imdb_score"),
                    item.get("poster_path"),
                ),
            )
        self.conn.commit()
        return item

    def close_spider(self, spider):
        self.conn.close()
