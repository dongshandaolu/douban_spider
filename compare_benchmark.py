"""
对比「requests + main_requests」与「Scrapy douban_top250」的耗时与核心代码规模，并生成图表。

用法（在项目根目录或 scrapy_project 下均可）::

    python compare_benchmark.py

默认只跑 1 页（25 条详情）以降低对豆瓣的压力；可通过环境变量调整::

    set BENCHMARK_MAX_PAGES=2
    python compare_benchmark.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

# 仓库根目录（spider/）与 Scrapy 项目根（spider/scrapy_project/）
_SCRAPY_PROJ = Path(__file__).resolve().parent
_ROOT = _SCRAPY_PROJ.parent
os.chdir(_SCRAPY_PROJ)
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import matplotlib.pyplot as plt

# 图表输出目录
_OUT = _SCRAPY_PROJ / "output"
_OUT.mkdir(parents=True, exist_ok=True)


def _count_lines(paths: list[Path]) -> int:
    n = 0
    for p in paths:
        if p.is_file():
            n += sum(1 for _ in p.open(encoding="utf-8", errors="ignore"))
    return n


def run_requests_benchmark(max_pages: int) -> float:
    """复用 main_requests 的会话与 acquire_movie（含页间 random_delay）。"""
    import requests

    from main_requests import acquire_movie, cookies, headers, _merge_cookies_from_env
    from utils import random_delay

    session = requests.Session()
    session.headers.update(headers)
    session.cookies.update(_merge_cookies_from_env(cookies))

    rows: list[dict] = []
    rank_state = [0]

    t0 = time.perf_counter()
    buf = StringIO()
    with redirect_stdout(buf):
        for i in range(0, max_pages * 25, 25):
            acquire_movie(i, session, rows, rank_state)
            random_delay()
    return time.perf_counter() - t0


def run_scrapy_benchmark(max_pages: int, concurrent: int, download_delay: float) -> float:
    """子进程启动 scrapy crawl，避免同一进程内 Twisted reactor 不可重启。"""
    cmd = [
        sys.executable,
        "-m",
        "scrapy",
        "crawl",
        "douban_top250",
        "-a",
        f"max_pages={max_pages}",
        "-s",
        "LOG_ENABLED=False",
        "-s",
        "ITEM_PIPELINES={}",
        "-s",
        f"CONCURRENT_REQUESTS={concurrent}",
        "-s",
        f"DOWNLOAD_DELAY={download_delay}",
        "-s",
        "RANDOMIZE_DOWNLOAD_DELAY=False",
        "-s",
        "ROBOTSTXT_OBEY=False",
    ]
    t0 = time.perf_counter()
    subprocess.run(
        cmd,
        cwd=str(_SCRAPY_PROJ),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return time.perf_counter() - t0


def _plot_times(labels: list[str], seconds: list[float], path: Path) -> None:
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(figsize=(8, 4.5))
    colors = ["#4472C4", "#ED7D31", "#70AD47"][: len(labels)]
    ax.bar(labels, seconds, color=colors)
    ax.set_ylabel("耗时（秒）")
    ax.set_title("豆瓣 Top250 采样爬取： wall time 对比")
    for i, v in enumerate(seconds):
        ax.text(i, v, f"{v:.2f}s", ha="center", va="bottom", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _plot_loc(labels: list[str], locs: list[int], path: Path) -> None:
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(labels, locs, color=["#5B9BD5", "#F4B183"])
    ax.set_ylabel("行数（LOC，含空行与注释）")
    ax.set_title("核心模块代码量对比（粗略）")
    for i, v in enumerate(locs):
        ax.text(i, v, str(v), ha="center", va="bottom", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    max_pages = int(os.environ.get("BENCHMARK_MAX_PAGES", "1"))
    max_pages = max(1, min(max_pages, 10))

    t_req = run_requests_benchmark(max_pages)
    # 与 requests「页内连续请求、页间有延迟」更接近：并发 1、无下载延迟
    t_scrapy_seq = run_scrapy_benchmark(max_pages, concurrent=1, download_delay=0.0)
    # 展示 Scrapy 并发优势：多并发 + 无延迟（压测意味更强，仅作能力对比）
    t_scrapy_par = run_scrapy_benchmark(max_pages, concurrent=8, download_delay=0.0)

    print(f"采样页数: {max_pages}（每页 25 条详情）")
    print(f"requests + main_requests:     {t_req:.2f} s")
    print(f"Scrapy 并发=1 / DOWNLOAD_DELAY=0: {t_scrapy_seq:.2f} s")
    print(f"Scrapy 并发=8 / DOWNLOAD_DELAY=0: {t_scrapy_par:.2f} s")

    time_png = _OUT / "benchmark_wall_time.png"
    _plot_times(
        ["requests\n(含页间 random_delay)", "Scrapy\n并发=1", "Scrapy\n并发=8"],
        [t_req, t_scrapy_seq, t_scrapy_par],
        time_png,
    )
    print(f"已保存耗时对比图: {time_png}")

    requests_loc = _count_lines([_ROOT / "main_requests.py"])
    scrapy_paths = [
        _SCRAPY_PROJ / "moviebot" / "items.py",
        _SCRAPY_PROJ / "moviebot" / "middlewares.py",
        _SCRAPY_PROJ / "moviebot" / "pipelines.py",
        _SCRAPY_PROJ / "moviebot" / "spiders" / "douban_top250_spider.py",
        _SCRAPY_PROJ / "moviebot" / "douban_defaults.py",
        _SCRAPY_PROJ / "moviebot" / "settings.py",
    ]
    scrapy_loc = _count_lines(scrapy_paths)

    loc_png = _OUT / "benchmark_loc.png"
    _plot_loc(["main_requests.py\n（单文件）", "Scrapy 核心拆分\n（Item+MW+Pipe+Spider+配置）"], [requests_loc, scrapy_loc], loc_png)
    print(f"已保存 LOC 对比图: {loc_png}")

    print("\n说明：")
    print("- requests 版在页与页之间调用 utils.random_delay()；Scrapy 两条曲线关闭 Pipeline 且 DOWNLOAD_DELAY=0，仅对比抓取吞吐。")
    print("- 「并发=8」更易发挥 Scrapy 异步调度优势；生产环境请自行加延迟与重试策略，遵守站点规则。")


if __name__ == "__main__":
    main()
