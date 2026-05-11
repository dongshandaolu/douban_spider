# db.py
import sqlite3
from pathlib import Path

from settings import DATA_DIR

DB_PATH = DATA_DIR / "movie.db"

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

    # requests 脚本「豆瓣 Top250 详情」专用表，与 Scrapy 的 movies 结构独立
    cur.execute("""
        CREATE TABLE IF NOT EXISTS douban_top250 (
            title TEXT PRIMARY KEY,
            detail_url TEXT,
            year TEXT,
            director TEXT,
            writer TEXT,
            actors TEXT,
            area TEXT,
            plot TEXT,
            language TEXT,
            alias TEXT,
            score TEXT,
            synopsis TEXT,
            comment_number TEXT,
            image_url TEXT,
            rank_num INTEGER
        )
    """)

    _migrate_douban_top250_extra(conn)

    conn.commit()
    conn.close()


def _migrate_douban_top250_extra(conn: sqlite3.Connection) -> None:
    """为 douban_top250 增加 Selenium 详情补充字段（若不存在）。"""
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(douban_top250)")
    existing = {row[1] for row in cur.fetchall()}
    for col, typ in (
        ("duration", "TEXT"),
        ("genre", "TEXT"),
        ("imdb_ref", "TEXT"),
        ("poster_local", "TEXT"),
    ):
        if col not in existing:
            try:
                cur.execute(
                    f"ALTER TABLE douban_top250 ADD COLUMN {col} {typ}"
                )
            except sqlite3.OperationalError:
                pass
    conn.commit()


def update_douban_top250_selenium_fields(
    title: str,
    *,
    duration: str = "",
    genre: str = "",
    imdb_ref: str = "",
    poster_local: str = "",
) -> None:
    """更新单条 Top250 记录的片长、类型、IMDb、本地海报路径。"""
    init_db()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    _migrate_douban_top250_extra(conn)
    conn.execute(
        """
        UPDATE douban_top250 SET
            duration = COALESCE(NULLIF(?, ''), duration),
            genre = COALESCE(NULLIF(?, ''), genre),
            imdb_ref = COALESCE(NULLIF(?, ''), imdb_ref),
            poster_local = COALESCE(NULLIF(?, ''), poster_local)
        WHERE title = ?
        """,
        (duration, genre, imdb_ref, poster_local, title),
    )
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

def save_douban_top250_batch(rows: list[dict], replace_all: bool = False):
    """将 main_requests 爬取的 Top250 详情批量写入 douban_top250 表。

    replace_all=True 时先清空表，避免本次未出现的旧记录残留。
    """
    if not rows:
        return
    init_db()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    if replace_all:
        conn.execute("DELETE FROM douban_top250")
    conn.executemany(
        """
        INSERT OR REPLACE INTO douban_top250 (
            title, detail_url, year, director, writer, actors, area, plot,
            language, alias, score, synopsis, comment_number, image_url, rank_num
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                r.get("title"),
                r.get("detail_url"),
                r.get("year"),
                r.get("director"),
                r.get("writer"),
                r.get("actors"),
                r.get("area"),
                r.get("plot"),
                r.get("language"),
                r.get("alias"),
                r.get("score"),
                r.get("synopsis"),
                r.get("comment_number"),
                r.get("image_url"),
                r.get("rank_num"),
            )
            for r in rows
        ],
    )
    conn.commit()
    conn.close()


def ensure_movie_exists(title: str, detail_url: str = "") -> None:
    """保证 movies 中存在 title，以满足 comments 外键（Top250 数据可能在 douban_top250 ）。"""
    if not title:
        return
    init_db()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT OR IGNORE INTO movies (title, detail_url) VALUES (?, ?)",
        (title, detail_url or None),
    )
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
