import json
import os
import re
import time
import random
from typing import Any

import pandas as pd
import requests
from lxml import etree

from db import init_db, save_douban_top250_batch
from settings import DATA_DIR, DELAY_RANGE, DOUBAN_COOKIE_ENV, RETRY, TIMEOUT
from utils import get_logger, random_delay

logger = get_logger("main_requests", "logs/main_requests.log")

cookies = {
    '__utmv': '30149280.29504',
    '__utmz': '30149280.1778494997.15.5.utmcsr=cn.bing.com|utmccn=(referral)|utmcmd=referral|utmcct=/',
    '__utmz': '223695111.1778494997.8.3.utmcsr=cn.bing.com|utmccn=(referral)|utmcmd=referral|utmcct=/',
    '_pk_id.100001.4cf6': 'ec50f6087551a9c8.1778420889.',
    '_pk_id.100001.8cb4': '6cffda50510a75ec.1777535510.',
    '_pk_ref.100001.4cf6': '%5B%22%22%2C%22%22%2C1778494997%2C%22https%3A%2F%2Fcn.bing.com%2F%22%5D',
    '_pk_ref.100001.8cb4': '%5B%22%22%2C%22%22%2C1778492534%2C%22https%3A%2F%2Fcn.bing.com%2F%22%5D',
    '_pk_ses.100001.4cf6': '1',
    '_vwo_uuid_v2': 'DEF184B8F7AA48402AC538664313CDF9B|3ac3981632eca1ca44a50cd5f446df86',
    'ap_v': '0,6.0',
    'bid': 'vqXR3IQIWws',
    'ck': 'HKYm',
    'dbcl2': '"295041788:aj+6/Ksi+ig"',
    'frodotk_db': '"7f629c1439d17cc57e27d43cad74764f"',
    'll': '"118254"',
    'push_doumail_num': '0',
    'push_noty_num': '0',
}

headers = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'priority': 'u=0, i',
    'referer': 'https://movie.douban.com/top250',
    'sec-ch-ua': '"Not)A;Brand";v="99", "Microsoft Edge";v="127", "Chromium";v="127"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-user': '?1',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0',
}

all_data = []


def _merge_cookies_from_env(base: dict) -> dict:
    raw = os.environ.get(DOUBAN_COOKIE_ENV, "").strip()
    if not raw:
        return dict(base)
    extra = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            extra[k.strip()] = v.strip()
    return {**base, **extra}


def _session_get(session: requests.Session, url: str, **kwargs) -> requests.Response | None:
    kwargs.setdefault("timeout", TIMEOUT)
    last_exc: Exception | None = None
    for attempt in range(RETRY):
        try:
            r = session.get(url, **kwargs)
            return r
        except requests.RequestException as e:
            last_exc = e
            wait = random.uniform(*DELAY_RANGE)
            logger.warning("请求失败 %s 第 %s/%s 次: %s，%.1fs 后重试", url, attempt + 1, RETRY, e, wait)
            time.sleep(wait)
    logger.error("请求放弃 %s: %s", url, last_exc)
    return None


def _first_text(nodes: list[Any], default: str = "") -> str:
    if not nodes:
        return default
    t = nodes[0]
    return t if isinstance(t, str) else str(t)


def acquire_movie(page_start: int, session: requests.Session, rows: list[dict], rank_state: list[int]) -> None:
    params = {
        'start': f'{page_start}',
        'filter': '',
    }

    response = _session_get(
        session,
        'https://movie.douban.com/top250',
        params=params,
    )
    if response is None or response.status_code != 200:
        code = response.status_code if response else "无响应"
        print(f'列表页请求失败，状态码：{code}')
        return

    html = etree.HTML(response.text)
    hrefs = html.xpath('//*[@id="content"]/div/div[1]/ol/li/div/div[2]/div[1]/a/@href')

    for href in hrefs:
        response = _session_get(session, href)
        if response is None or response.status_code != 200:
            code = response.status_code if response else "无响应"
            print(f'详情页请求失败 {href}，状态码：{code}')
            continue

        html2 = etree.HTML(response.text)

        # 电影名
        title = _first_text(html2.xpath('//*[@id="content"]/h1/span[1]/text()'))
        if not title:
            logger.warning("跳过无标题页: %s", href)
            continue
        yraw = _first_text(html2.xpath('//*[@id="content"]/h1/span[2]/text()'))
        year = yraw[1:-1] if len(yraw) >= 3 else yraw

        # 导演
        director = _first_text(html2.xpath('//*[@id="info"]/span[1]/span[2]/a/text()'))

        # 编剧（可能不存在）
        try:
            writer = html2.xpath('//*[@id="info"]/span[2]/span[2]/a/text()')[0]
        except (IndexError, TypeError):
            writer = ''

        # 剧情类型
        plot = _first_text(html2.xpath('//*[@id="info"]/span[5]/text()'))

        # 评分
        score = _first_text(html2.xpath('//*[@id="interest_sectl"]/div[1]/div[2]/strong/text()'))

        # 剧情简介
        synopsis = html2.xpath('//*[@id="link-report-intra"]/span/text()')

        # 评论数
        comment_raw = _first_text(html2.xpath('//*[@id="comments-section"]/div[1]/h2/span/a/text()'))
        comment_number = comment_raw.split(' ')[1] if len(comment_raw.split(' ')) > 1 else comment_raw

        # 海报地址
        image_url = _first_text(html2.xpath('//*[@id="mainpic"]/a/img/@src'))

        # 地区、语言、别名
        temps = html2.xpath('//*[@id="info"]/text()')
        new_temp = []
        for temp in temps:
            temp = temp.replace(' ', '')
            if ('\n' not in temp) and (temp != '/') and (temp != ''):
                new_temp.append(temp)

        area = new_temp[0] if len(new_temp) > 0 else ""
        language = new_temp[1] if len(new_temp) > 1 else ""
        alias = new_temp[-2] if len(new_temp) >= 2 else ""

        # ---------- 演员提取（修复后） ----------
        actors = []
        # 方案一：尝试从 ld+json 提取（兼容旧版页面）
        try:
            data = re.findall('<script type="application/ld+json">(.*?)</script>', response.text, re.DOTALL)[0]
            data = data.replace('\n', '').replace('\t', "")
            json_data = json.loads(data)
            actors = [act['name'] for act in json_data.get('actor', [])]
        except (IndexError, json.JSONDecodeError, KeyError, TypeError):
            # 方案二：直接从 info 区域通过 XPath 提取演员
            actor_nodes = html2.xpath('//span[@class="actor"]/span[@class="attrs"]/a/text()')
            # 如果没有 class="actor" 的 span，尝试更通用的路径
            if not actor_nodes:
                actor_nodes = html2.xpath('//*[@id="info"]//span[contains(text(),"主演")]/following-sibling::span[1]/a/text()')
            actors = actor_nodes if actor_nodes else []
        # ---------------------------------------

        rank_state[0] += 1
        synopsis_str = "\n".join(synopsis) if isinstance(synopsis, list) else str(synopsis)
        actors_str = json.dumps(actors, ensure_ascii=False)

        data = [title, year, director, writer, actors, area, plot, language, alias, score, synopsis, comment_number, image_url]
        all_data.append(data)
        print(title, score)

        rows.append({
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
            "synopsis": synopsis_str,
            "comment_number": comment_number,
            "image_url": image_url,
            "rank_num": rank_state[0],
        })


def _persist_outputs(rows: list[dict]) -> None:
    if not rows:
        logger.warning("无数据可写入")
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    save_douban_top250_batch(rows, replace_all=True)

    columns = ['电影名', '年份', '导演', '编剧', '主演', '地区', '剧情', '语言', '又名', '评分', '剧情介绍', '评论数', '海报地址']
    table_rows = []
    for r in rows:
        try:
            actors_list = json.loads(r["actors"]) if r.get("actors") else []
        except json.JSONDecodeError:
            actors_list = []
        actors_cell = " / ".join(actors_list) if isinstance(actors_list, list) else str(r.get("actors", ""))
        table_rows.append([
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
        ])
    result = pd.DataFrame(table_rows, columns=columns)
    csv_path = DATA_DIR / "movie.csv"
    result.to_csv(csv_path, index=False, encoding="utf-8-sig")

    json_path = DATA_DIR / "movie.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    logger.info("已写入 %s、%s；SQLite 表 douban_top250 -> %s", csv_path, json_path, DATA_DIR / "movie.db")


if __name__ == '__main__':
    session = requests.Session()
    session.headers.update(headers)
    session.cookies.update(_merge_cookies_from_env(cookies))

    rows_out: list[dict] = []
    rank_state = [0]

    for i in range(0, 250, 25):
        print(f'--------第{i//25 + 1}页---------')
        acquire_movie(i, session, rows_out, rank_state)
        random_delay()

    _persist_outputs(rows_out)
