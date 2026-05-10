import json
import re
import time
from typing import Any

import pandas as pd
import requests
from lxml import etree

from db import init_db, save_douban_top250_batch
from settings import DATA_DIR, TIMEOUT
from utils import get_logger, norm_text, random_delay

logger = get_logger("main_requests", "logs/main_requests.log")

cookies = {
    "ll": '"118282"',
    "bid": "qpeBkdWNQ30",
    "__utma": "30149280.1285408772.1722931171.1722931171.1722931171.1",
    "__utmc": "30149280",
    "__utmz": "30149280.1722931171.1.1.utmcsr=cn.bing.com|utmccn=(referral)|utmcmd=referral|utmcct=/",
    "__utmt": "1",
    "__utmb": "30149280.1.10.1722931171",
    "__utma": "223695111.549597820.1722931184.1722931184.1722931184.1",
    "__utmb": "223695111.0.10.1722931184",
    "__utmc": "223695111",
    "__utmz": "223695111.1722931184.1.1.utmcsr=cn.bing.com|utmccn=(referral)|utmcmd=referral|utmcct=/",
    "_pk_ref.100001.4cf6": "%5B%22%22%2C%22%22%2C1722931184%2C%22https%3A%2F%2Fcn.bing.com%2F%22%5D",
    "_pk_id.100001.4cf6": "39e7e842a6abee49.1722931184.",
    "_pk_ses.100001.4cf6": "1",
    "ap_v": "0,6.0",
    "__yadk_uid": "5tRoftzrzq0L8EylRtLcRgAgQ8c6kVkb",
}

headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    "priority": "u=0, i",
    "referer": "https://movie.douban.com/top250",
    "sec-ch-ua": '"Not)A;Brand";v="99", "Microsoft Edge";v="127", "Chromium";v="127"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0",
}

COLUMNS_ZH = [
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


def _xpath_first(html: Any, xp: str, default: str = "") -> str:
    nodes = html.xpath(xp)
    if not nodes:
        return default
    val = nodes[0]
    if isinstance(val, etree._Element):
        t = val.xpath("string(.)")
        return norm_text(t) if t else default
    return norm_text(str(val)) if val is not None else default


def _actors_from_ld_json(html_text: str) -> list[str]:
    blocks = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>',
        html_text,
        re.DOTALL,
    )
    for raw in blocks:
        raw = raw.replace("\n", "").replace("\r", "").replace("\t", "")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        actors_raw = data.get("actor")
        if not actors_raw:
            continue
        if isinstance(actors_raw, dict):
            name = actors_raw.get("name")
            return [name] if name else []
        out: list[str] = []
        for act in actors_raw:
            if isinstance(act, dict) and act.get("name"):
                out.append(act["name"])
        return out
    return []


def _parse_info_region_language_alias(html2: etree._Element) -> tuple[str, str, str]:
    """从 #info 的纯文本节点解析地区、语言、又名（与豆瓣常见排版一致）。"""
    temps = html2.xpath('//*[@id="info"]/text()')
    new_temp: list[str] = []
    for temp in temps:
        temp = (temp or "").replace(" ", "")
        if ("\n" not in temp) and (temp != "/") and (temp != ""):
            new_temp.append(temp)
    area, language, alias = "", "", ""
    try:
        area = new_temp[0]
        language = new_temp[1]
        alias = new_temp[-2] if len(new_temp) >= 2 else ""
    except IndexError:
        pass
    return area, language, alias


def scrape_one_detail(href: str, rank_num: int) -> dict[str, Any] | None:
    random_delay()
    try:
        response = requests.get(
            href, cookies=cookies, headers=headers, timeout=TIMEOUT
        )
        response.raise_for_status()
    except requests.RequestException as e:
        logger.warning("请求详情失败 %s: %s", href, e)
        return None

    html2 = etree.HTML(response.text)
    if html2 is None:
        return None

    title = _xpath_first(html2, '//*[@id="content"]/h1/span[1]/text()')
    if not title:
        logger.warning("无标题，跳过: %s", href)
        return None

    year_raw = _xpath_first(html2, '//*[@id="content"]/h1/span[2]/text()')
    year = year_raw[1:-1] if len(year_raw) >= 2 else year_raw

    director = _xpath_first(html2, '//*[@id="info"]/span[1]/span[2]/a/text()')
    writer_nodes = html2.xpath('//*[@id="info"]/span[2]/span[2]/a/text()')
    writer = writer_nodes[0] if writer_nodes else ""

    plot = _xpath_first(html2, '//*[@id="info"]/span[5]/text()')
    score = _xpath_first(
        html2, '//*[@id="interest_sectl"]/div[1]/div[2]/strong/text()'
    )

    synopsis_parts = html2.xpath('//*[@id="link-report-intra"]//text()')
    synopsis = norm_text("".join(synopsis_parts))

    comment_raw = _xpath_first(
        html2, '//*[@id="comments-section"]/div[1]/h2/span/a/text()'
    )
    comment_number = ""
    if comment_raw:
        parts = comment_raw.split()
        if len(parts) >= 2:
            comment_number = parts[1]

    image_url = _xpath_first(html2, '//*[@id="mainpic"]/a/img/@src')

    area, language, alias = _parse_info_region_language_alias(html2)
    actors_list = _actors_from_ld_json(response.text)
    actors_str = json.dumps(actors_list, ensure_ascii=False)

    return {
        "title": title,
        "detail_url": href,
        "year": year,
        "director": director,
        "writer": writer,
        "actors": actors_str,
        "area": area,
        "plot": plot,
        "language": language,
        "alias": alias,
        "score": score,
        "synopsis": synopsis,
        "comment_number": comment_number,
        "image_url": image_url,
        "rank_num": rank_num,
        "_actors_list": actors_list,
    }


def acquire_page(page_start: int, rank_counter: list[int]) -> list[dict[str, Any]]:
    """爬取 Top250 某一列表页上的所有详情。"""
    params = {"start": str(page_start), "filter": ""}
    random_delay()
    try:
        response = requests.get(
            "https://movie.douban.com/top250",
            params=params,
            cookies=cookies,
            headers=headers,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error("列表页失败 start=%s: %s", page_start, e)
        return []

    html = etree.HTML(response.text)
    if html is None:
        return []

    hrefs = html.xpath(
        '//*[@id="content"]/div/div[1]/ol/li/div/div[2]/div[1]/a/@href'
    )
    rows: list[dict[str, Any]] = []
    for href in hrefs:
        rank_counter[0] += 1
        row = scrape_one_detail(href, rank_counter[0])
        if row is None:
            continue
        rows.append(row)
        logger.info("已采集 %s", row["title"])
    return rows


def save_outputs(rows: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path_csv = DATA_DIR / "movie.csv"
    path_json = DATA_DIR / "movie.json"
    path_db = DATA_DIR / "movie.db"

    for r in rows:
        r.pop("_actors_list", None)

    table_rows = []
    for r in rows:
        table_rows.append(
            {
                "title": r["title"],
                "detail_url": r.get("detail_url", ""),
                "year": r.get("year", ""),
                "director": r.get("director", ""),
                "writer": r.get("writer", ""),
                "actors": r.get("actors", "[]"),
                "area": r.get("area", ""),
                "plot": r.get("plot", ""),
                "language": r.get("language", ""),
                "alias": r.get("alias", ""),
                "score": r.get("score", ""),
                "synopsis": r.get("synopsis", ""),
                "comment_number": r.get("comment_number", ""),
                "image_url": r.get("image_url", ""),
                "rank_num": r.get("rank_num"),
            }
        )

    list_for_files = []
    for r in rows:
        actors_parsed = json.loads(r.get("actors") or "[]")
        actors_csv = " / ".join(actors_parsed) if isinstance(actors_parsed, list) else ""
        list_for_files.append(
            [
                r["title"],
                r.get("year", ""),
                r.get("director", ""),
                r.get("writer", ""),
                actors_csv,
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

    df = pd.DataFrame(list_for_files, columns=COLUMNS_ZH)
    df.to_csv(path_csv, index=False, encoding="utf-8-sig")

    json_records = []
    for r in rows:
        json_records.append(
            {
                "电影名": r["title"],
                "年份": r.get("year", ""),
                "导演": r.get("director", ""),
                "编剧": r.get("writer", ""),
                "主演": json.loads(r.get("actors") or "[]"),
                "地区": r.get("area", ""),
                "剧情": r.get("plot", ""),
                "语言": r.get("language", ""),
                "又名": r.get("alias", ""),
                "评分": r.get("score", ""),
                "剧情介绍": r.get("synopsis", ""),
                "评论数": r.get("comment_number", ""),
                "海报地址": r.get("image_url", ""),
                "详情链接": r.get("detail_url", ""),
                "排名": r.get("rank_num"),
            }
        )
    path_json.write_text(
        json.dumps(json_records, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    init_db()
    save_douban_top250_batch(table_rows, replace_all=True)
    logger.info(
        "已写入 %s、%s；SQLite 表 douban_top250 -> %s",
        path_csv,
        path_json,
        path_db,
    )


def main() -> None:
    all_rows: list[dict[str, Any]] = []
    rank_counter = [0]
    for i in range(0, 250, 25):
        logger.info("-------- 第 %s 页 ---------", i // 25 + 1)
        all_rows.extend(acquire_page(i, rank_counter))
        time.sleep(1)

    if not all_rows:
        logger.error("未获取到任何数据")
        return

    save_outputs(all_rows)
    print(f"共 {len(all_rows)} 条，已保存到 {DATA_DIR / 'movie.csv'} 等文件。")


if __name__ == "__main__":
    main()
