BOT_NAME = "moviebot"
SPIDER_MODULES = ["moviebot.spiders"]
NEWSPIDER_MODULE = "moviebot.spiders"

# 与 requests 版一致：不强制遵守 robots（main_requests 未检查 robots.txt）
ROBOTSTXT_OBEY = False

CONCURRENT_REQUESTS = 8
DOWNLOAD_DELAY = 1
RANDOMIZE_DOWNLOAD_DELAY = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 522, 524, 408, 429, 403]
LOG_LEVEL = "INFO"

# 消除 Scrapy 关于 REQUEST_FINGERPRINTER_IMPLEMENTATION 的弃用提示
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"

UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]

PROXY_LIST = []

ITEM_PIPELINES = {
    "moviebot.pipelines.DoubanTop250Pipeline": 250,
    "moviebot.pipelines.SqlitePipeline": 300,
}

DOWNLOADER_MIDDLEWARES = {
    "moviebot.middlewares.RandomUserAgentMiddleware": 542,
    "moviebot.middlewares.DoubanHeadersMiddleware": 543,
    "moviebot.middlewares.SimpleProxyMiddleware": 544,
}
