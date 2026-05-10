import re
import json
import time
import random
import os
import sqlite3
import shutil
import requests
import pandas as pd
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ========== 全局配置 ==========
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}
REQUEST_DELAY = (1.5, 3.5)

# 创建数据文件夹
os.makedirs('data', exist_ok=True)
os.makedirs('images', exist_ok=True)


def get_session():
    """创建带重试机制的会话，提高稳定性"""
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.headers.update(HEADERS)
    return session


def safe_xpath_first(tree, xpath, default=''):
    """安全获取第一个XPath结果，避免IndexError"""
    result = tree.xpath(xpath)
    return result[0].strip() if result else default


def sanitize_filename(filename):
    """清理文件名中的特殊字符，避免保存失败"""
    illegal_chars = r'[\/:*?"<>|]'
    return re.sub(illegal_chars, '_', filename)


def download_poster(session, image_url, movie_name, year):
    """下载海报图片到images文件夹"""
    if not image_url:
        print(f'    无海报地址，跳过下载')
        return

    # 生成安全的文件名
    safe_name = sanitize_filename(f'{movie_name}_{year}')
    # 提取图片后缀
    ext = image_url.split('.')[-1]
    if len(ext) > 5:  # 防止后缀异常（比如带参数）
        ext = 'jpg'
    save_path = f'images/{safe_name}.{ext}'

    try:
        resp = session.get(image_url, timeout=10, stream=True)
        resp.raise_for_status()
        with open(save_path, 'wb') as f:
            shutil.copyfileobj(resp.raw, f)
        print(f'    海报已保存至: {save_path}')
    except Exception as e:
        print(f'    海报下载失败 {image_url}: {e}')


def parse_movie_detail(session, url):
    """解析单部电影详情页，返回字段字典"""
    # 随机延时，降低请求频率
    time.sleep(random.uniform(*REQUEST_DELAY))

    try:
        resp = session.get(url, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f'请求失败 {url}: {e}')
        return None

    # 解析HTML
    from lxml import etree
    tree = etree.HTML(resp.text)

    # ---------- 从 JSON-LD 提取元数据 ----------
    ld_json = re.search(r'<script type="application/ld\+json">(.*?)</script>', resp.text, re.DOTALL)
    meta = {}
    if ld_json:
        try:
            meta = json.loads(ld_json.group(1))
        except Exception:
            meta = {}

    # 电影名
    title = meta.get('name', '') or safe_xpath_first(tree, '//span[@property="v:itemreviewed"]/text()')
    # 年份
    year = ''
    date_pub = meta.get('datePublished', '')
    if date_pub:
        year = str(date_pub)[:4]
    if not year:
        year_raw = safe_xpath_first(tree, '//span[@class="year"]/text()')
        year_match = re.search(r'\d{4}', year_raw)
        if year_match:
            year = year_match.group()

    rating = meta.get('aggregateRating', {}).get('ratingValue', '')
    if not rating:
        rating = safe_xpath_first(tree, '//strong[@property="v:average"]/text()')

    directors = meta.get('director', [])
    if isinstance(directors, list):
        director = ', '.join([d.get('name', '') for d in directors if d.get('name')])
    else:
        director = safe_xpath_first(tree, "//span[contains(text(),'导演')]/following-sibling::span[1]//a/text()")

    actors = meta.get('actor', [])
    actor_names = [a.get('name', '') for a in actors if a.get('name')]
    actors_str = ', '.join(actor_names)
    # 类型
    genres = meta.get('genre', [])
    if genres:
        plot = ' / '.join(genres)
    else:
        genre_spans = tree.xpath('//span[@property="v:genre"]/text()')
        plot = ' / '.join([g.strip() for g in genre_spans])
    # 海报
    image_url = meta.get('image', '') or safe_xpath_first(tree, '//*[@id="mainpic"]/a/img/@src')

    # ---------- 页面字段（JSON里没有的）----------
    # 编剧
    writer = safe_xpath_first(tree, "//span[contains(text(),'编剧')]/following-sibling::span[1]//a/text()")
    # 地区
    area = safe_xpath_first(tree, "//span[contains(text(),'制片国家/地区')]/following-sibling::text()[1]")
    if not area:
        area_texts = tree.xpath('//*[@id="info"]/text()')
        area = next((t.strip() for t in area_texts if t.strip() and '/' not in t and ':' not in t), '')

    language = safe_xpath_first(tree, "//span[contains(text(),'语言')]/following-sibling::text()[1]")

    alias = safe_xpath_first(tree, "//span[contains(text(),'又名')]/following-sibling::text()[1]")
    # 简介
    synopsis_list = tree.xpath('//*[@id="link-report-intra"]/span/text()')
    synopsis = ' '.join([s.strip() for s in synopsis_list if s.strip()])

    comment_text = safe_xpath_first(tree, '//*[@id="comments-section"]/div[1]/h2/span/a/text()')
    comment_number = ''
    if comment_text:
        num_match = re.search(r'\d+', comment_text.replace(',', ''))
        if num_match:
            comment_number = num_match.group()

    # 下载海报
    download_poster(session, image_url, title, year)

    return {
        '电影名': title,
        '年份': year,
        '导演': director,
        '编剧': writer,
        '主演': actors_str,
        '地区': area,
        '剧情': plot,
        '语言': language,
        '又名': alias,
        '评分': rating,
        '剧情介绍': synopsis,
        '评论数': comment_number,
        '海报地址': image_url,
    }


def crawl_douban_top250():
    """爬取豆瓣TOP250全部电影信息"""
    session = get_session()
    all_data = []

    for page_start in range(0, 250, 25):
        page_no = page_start // 25 + 1
        print(f'正在抓取第 {page_no} 页 (start={page_start})')
        params = {'start': page_start, 'filter': ''}
        try:
            resp = session.get('https://movie.douban.com/top250', params=params, timeout=10)
            resp.raise_for_status()
        except Exception as e:
            print(f'列表页请求失败: {e}')
            continue

        from lxml import etree
        tree = etree.HTML(resp.text)
        hrefs = tree.xpath('//*[@id="content"]/div/div[1]/ol/li/div/div[2]/div[1]/a/@href')
        print(f'找到 {len(hrefs)} 部电影链接')

        for href in hrefs:
            print(f'  正在处理 {href}')
            movie = parse_movie_detail(session, href)
            if movie:
                all_data.append(movie)
                print(f'    电影名: {movie["电影名"]}, 评分: {movie["评分"]}')

    return all_data


def save_data(all_data):
    if not all_data:
        print('无数据可保存')
        return

    df = pd.DataFrame(all_data)
    column_order = ['电影名', '年份', '导演', '编剧', '主演', '地区', '剧情', '语言', '又名', '评分', '剧情介绍',
                    '评论数', '海报地址']
    df = df[column_order]

    # 1. 保存为CSV
    csv_path = 'data/movie.csv'
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f'\nCSV文件已保存至: {csv_path}')

    # 2. 保存为JSON
    json_path = 'data/movie.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=4)
    print(f'JSON文件已保存至: {json_path}')

    # 3. 保存为SQLite数据库
    db_path = 'data/movie.db'
    conn = sqlite3.connect(db_path)
    df.to_sql('movie_top250', conn, if_exists='replace', index=False)
    conn.commit()
    conn.close()
    print(f'SQLite数据库已保存至: {db_path}')


if __name__ == '__main__':
    movies_data = crawl_douban_top250()
    if movies_data:
        save_data(movies_data)
    else:
        print('未获取到任何数据，请检查网络或页面结构')
