# db.py
import sqlite3
from pathlib import Path
from utils import safe_filename

DB_PATH = Path("data/movie.db")

def init_db():
    """初始化数据库和表结构，与 Scrapy pipeline 保持一致"""
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            title TEXT PRIMARY KEY,
            title_en TEXT,
            rank_num INTEGER,
            score REAL,
            vote_count INTEGER,
            director TEXT,
            intro TEXT,
            detail_url TEXT,
            year TEXT,
            duration TEXT,
            genre TEXT,
            imdb_score TEXT,
            poster_path TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            movie_title TEXT,
            commenter TEXT,
            comment_score TEXT,
            content TEXT,
            comment_time TEXT,
            detail_url TEXT,
            FOREIGN KEY (movie_title) REFERENCES movies(title)
        )
    """)

    conn.commit()
    conn.close()

def upsert_movie(movie: dict):
    """插入或更新电影记录，title 为主键"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("""
        INSERT OR REPLACE INTO movies (
            title, title_en, rank_num, score, vote_count,
            director, intro, detail_url, year, duration,
            genre, imdb_score, poster_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        movie.get("title"),
        movie.get("title_en"),
        movie.get("rank_num"),
        movie.get("score"),
        movie.get("vote_count"),
        movie.get("director"),
        movie.get("intro"),
        movie.get("detail_url"),
        movie.get("year"),
        movie.get("duration"),
        movie.get("genre"),
        movie.get("imdb_score"),
        movie.get("poster_path"),
    ))
    conn.commit()
    conn.close()

def insert_comment(comment: dict):
    """插入一条短评记录"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("""
        INSERT INTO comments (
            movie_title, commenter, comment_score,
            content, comment_time, detail_url
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        comment.get("movie_title"),
        comment.get("commenter"),
        comment.get("comment_score"),
        comment.get("content"),
        comment.get("comment_time"),
        comment.get("detail_url"),
    ))
    conn.commit()
    conn.close()
