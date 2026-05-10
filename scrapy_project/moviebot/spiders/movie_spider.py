import re

import scrapy
from bs4 import BeautifulSoup

from moviebot.items import MovieItem


class MovieSpider(scrapy.Spider):
    name = "movie"
    allowed_domains = ["movie.douban.com"]
    start_urls = [f"https://movie.douban.com/top250?start={i * 25}&filter=" for i in range(10)]

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

        year_match = re.search(r"(\d{4})", soup.get_text())
        item["year"] = year_match.group(1) if year_match else ""
        m = re.search(r"片长:\s*([^\n]+)", info)
        item["duration"] = m.group(1).strip() if m else ""
        m = re.search(r"类型:\s*([^\n]+)", info)
        item["genre"] = m.group(1).strip() if m else ""
        m = re.search(r"IMDb:\s*([0-9.]+)", info)
        item["imdb_score"] = m.group(1) if m else ""

        img = soup.select_one("a.nbgnbg img")
        item["poster_path"] = img["src"] if img and img.get("src") else ""
        yield item
