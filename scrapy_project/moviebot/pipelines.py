import sqlite3
from pathlib import Path


class SqlitePipeline:
    def open_spider(self, spider):
        self.db_path = Path("data/movie.db")
        self.db_path.parent.mkdir(exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
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
