import re
import time

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from db import init_db, insert_comment
from utils import norm_text

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
        if time_tag and time_tag.get("title"):
            comment_time = norm_text(time_tag.get("title"))
        else:
            comment_time = norm_text(time_tag.get_text() if time_tag else "")
        star = ""
        star_tag = c.select_one("span.comment-info span[class*='allstar']")
        if star_tag:
            star = " ".join(star_tag.get("class", []))
        rows.append(
            {
                "commenter": commenter,
                "content": content,
                "comment_time": comment_time,
                "comment_score": star,
            }
        )
    return rows


def crawl_comments(movie_title, movie_id, detail_url, limit=15):
    init_db()
    driver = build_driver()
    try:
        url = COMMENT_URL.format(mid=movie_id)
        driver.get(url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.comment-item")))

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


if __name__ == "__main__":
    # 演示：根据实际电影 subject id 修改
    mid = "1292052"
    comments = crawl_comments("示例电影", mid, f"https://movie.douban.com/subject/{mid}/")
    print(f"已抓取短评: {len(comments)}")
