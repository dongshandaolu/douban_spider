import scrapy


class DoubanTop250Item(scrapy.Item):
    """与 main_requests 写入 douban_top250 的字段一一对应。"""

    title = scrapy.Field()
    detail_url = scrapy.Field()
    year = scrapy.Field()
    director = scrapy.Field()
    writer = scrapy.Field()
    actors = scrapy.Field()
    area = scrapy.Field()
    plot = scrapy.Field()
    language = scrapy.Field()
    alias = scrapy.Field()
    score = scrapy.Field()
    synopsis = scrapy.Field()
    comment_number = scrapy.Field()
    image_url = scrapy.Field()
    rank_num = scrapy.Field()


class MovieItem(scrapy.Item):
    """原 movie 列表爬虫（movies 表）字段，保留兼容。"""

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
