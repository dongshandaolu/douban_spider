BOT_NAME = "moviebot"
SPIDER_MODULES = ["moviebot.spiders"]
NEWSPIDER_MODULE = "moviebot.spiders"

ROBOTSTXT_OBEY = True
CONCURRENT_REQUESTS = 8
DOWNLOAD_DELAY = 1
RETRY_TIMES = 3
LOG_LEVEL = "INFO"

UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]

PROXY_LIST = []

ITEM_PIPELINES = {
    "moviebot.pipelines.SqlitePipeline": 300,
}

DOWNLOADER_MIDDLEWARES = {
    "moviebot.middlewares.RandomUserAgentMiddleware": 543,
    "moviebot.middlewares.SimpleProxyMiddleware": 544,
}

