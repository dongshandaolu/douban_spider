"""
豆瓣电影数据：Pandas 清洗、统计分析、Matplotlib/Seaborn/Plotly 可视化，
以及 jieba + SnowNLP 短评情感与 TF-IDF 等 NLP 扩展；

数据目录默认使用项目根目录下的 data/，图表输出到 output/analysis/。
"""

from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

# Windows 终端下尽量用 UTF-8 输出中文
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from snownlp import SnowNLP
from sklearn.decomposition import LatentDirichletAllocation
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from wordcloud import WordCloud

warnings.filterwarnings("ignore", category=FutureWarning)

try:
    import plotly.express as px
    import plotly.graph_objects as go
except ImportError as e:  # pragma: no cover
    raise SystemExit("请安装 plotly: pip install plotly") from e

from cn_tokenizer import jieba_tokens as _jieba_tokens

# -----------------------------------------------------------------------------
# 路径与中文显示
# -----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output" / "analysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
sns.set_theme(style="whitegrid", font="Microsoft YaHei")

# Windows 常见中文字体（词云需要显式 font_path）
WIN_FONT = Path(r"C:\Windows\Fonts\msyh.ttc")
if not WIN_FONT.is_file():
    WIN_FONT = Path(r"C:\Windows\Fonts\simhei.ttf")


def _load_movies(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, encoding="utf-8")
    # 列「剧情」在 CSV 表头中表示类型/类型标签（与 JSON 中 plot 字段一致）
    rename_map = {
        "电影名": "title",
        "年份": "year",
        "导演": "director",
        "剧情": "genre",
        "评分": "score",
        "评论数": "review_count",
    }
    df = df.rename(columns=rename_map)
    for c in df.select_dtypes(include="object").columns:
        df[c] = df[c].apply(lambda x: x.strip() if isinstance(x, str) else x)

    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    df["review_count"] = pd.to_numeric(df["review_count"], errors="coerce")

    before = len(df)
    df = df.dropna(subset=["title", "score"]).drop_duplicates(subset=["title"], keep="first")
    deduped = before - len(df)
    print(f"[电影表] 去重剔除 {deduped} 条，剩余 {len(df)} 条")

    # 缺失：剧情介绍等非核心字段可保留
    return df


def _load_comments_jsonl(path: Path, limit: int | None) -> pd.DataFrame:
    rows = []
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            if limit is not None and i >= limit:
                break
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["text"] = df["text"].astype(str).str.strip()
    df = df[df["text"].str.len() > 0]
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    df["user_star"] = pd.to_numeric(df.get("rating"), errors="coerce")
    return df


def _sentiment_bucket(s: float) -> str:
    if s < 0.35:
        return "负面"
    if s > 0.65:
        return "正面"
    return "中性"


def _snownlp_scores(texts: list[str]) -> list[float]:
    scores = []
    for t in texts:
        try:
            scores.append(float(SnowNLP(t).sentiments))
        except Exception:
            scores.append(np.nan)
    return scores


def run_movie_stats(df: pd.DataFrame) -> None:
    print("\n=== 高分电影 Top10（按评分，评分相同按评论数） ===")
    top10 = df.sort_values(["score", "review_count"], ascending=[False, False]).head(10)
    print(top10[["title", "year", "score", "review_count", "director", "genre"]].to_string(index=False))

    print("\n=== 导演作品数量 Top15 ===")
    print(df["director"].value_counts().head(15))

    print("\n=== 类型分布（Top15） ===")
    print(df["genre"].value_counts().head(15))

    valid = df.dropna(subset=["score", "review_count"])
    r = valid["score"].corr(valid["review_count"])
    print(f"\n=== 评分 与 评论数 Pearson 相关系数: {r:.4f} ===")


def plot_figures_movies(df: pd.DataFrame) -> None:
    # 1) 评分直方图
    fig, ax = plt.subplots(figsize=(8, 4))
    sns.histplot(df["score"].dropna(), bins=20, kde=True, ax=ax, color="steelblue")
    ax.set_title("电影评分分布")
    ax.set_xlabel("评分")
    ax.set_ylabel("部数")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "hist_score.png", dpi=150)
    plt.close(fig)

    # 2) 类型饼图（取前 8 类，其余合并为「其他」）
    vc = df["genre"].fillna("未知").value_counts()
    head = vc.head(8)
    tail_sum = vc.iloc[8:].sum() if len(vc) > 8 else 0
    pie_vals = list(head.values)
    pie_labels = list(head.index)
    if tail_sum > 0:
        pie_vals.append(tail_sum)
        pie_labels.append("其他")
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.pie(pie_vals, labels=pie_labels, autopct="%1.1f%%", startangle=90)
    ax.set_title("电影类型占比（Top8 + 其他）")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "pie_genre.png", dpi=150)
    plt.close(fig)

    # 3) 散点图：评分 vs 评论数
    sub = df.dropna(subset=["score", "review_count"])
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.scatterplot(
        data=sub,
        x="review_count",
        y="score",
        alpha=0.35,
        hue="genre",
        legend=False,
        ax=ax,
        s=22,
    )
    ax.set_xscale("log")
    ax.set_title("评分 vs 评论数（横轴对数刻度）")
    ax.set_xlabel("评论数")
    ax.set_ylabel("评分")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "scatter_score_reviews.png", dpi=150)
    plt.close(fig)

    # 4) 时间趋势：按年份平均评分与上映数量
    by_year = df.dropna(subset=["year"]).groupby("year").agg(
        mean_score=("score", "mean"),
        n_titles=("title", "count"),
    )
    fig, ax1 = plt.subplots(figsize=(10, 4))
    ax2 = ax1.twinx()
    by_year["mean_score"].plot(ax=ax1, color="tab:blue", label="年均评分")
    by_year["n_titles"].plot(ax=ax2, color="tab:orange", alpha=0.7, label="每年影片数")
    ax1.set_ylabel("平均评分")
    ax2.set_ylabel("影片数量")
    ax1.set_title("按年份：平均评分与影片数量")
    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines + lines2, labels + labels2, loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "trend_year_score_count.png", dpi=150)
    plt.close(fig)


def plot_plotly_interactive(df: pd.DataFrame) -> None:
    sub = df.dropna(subset=["score", "review_count", "year"]).copy()
    fig = px.scatter(
        sub,
        x="review_count",
        y="score",
        color="genre",
        hover_data=["title", "director", "year"],
        log_x=True,
        title="交互式：评分 vs 评论数（Plotly）",
        labels={"review_count": "评论数", "score": "评分"},
    )
    fig.write_html(OUT_DIR / "plotly_scatter_score_reviews.html", include_plotlyjs="cdn")


def run_nlp_comments(comments: pd.DataFrame) -> None:
    if comments.empty:
        print("无短评数据，跳过 NLP。")
        return

    texts = comments["text"].tolist()
    print(f"\n[SnowNLP] 对 {len(texts)} 条短评计算情感分数…")
    comments = comments.copy()
    comments["snownlp_score"] = _snownlp_scores(texts)
    comments["sentiment_label"] = comments["snownlp_score"].apply(_sentiment_bucket)

    dist = comments["sentiment_label"].value_counts(normalize=True).reindex(["正面", "中性", "负面"]).fillna(0)
    print("\n=== 短评情感比例（SnowNLP，阈值 0.35 / 0.65） ===")
    print((dist * 100).round(2).astype(str) + "%")

    order = ["正面", "中性", "负面"]
    cnt = comments["sentiment_label"].value_counts().reindex(order).fillna(0)
    fig, ax = plt.subplots(figsize=(6, 4))
    cnt.plot(kind="bar", ax=ax, color=["#2ca02c", "#7f7f7f", "#d62728"])
    ax.set_title("短评情感分布（SnowNLP）")
    ax.set_xlabel("类别")
    ax.set_ylabel("条数")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "bar_sentiment_comments.png", dpi=150)
    plt.close(fig)

    # 与用户星级对比（若存在）
    star = comments["user_star"].dropna()
    if len(star) >= 10:
        comments_valid = comments.dropna(subset=["user_star", "snownlp_score"])
        ag = comments_valid.groupby("user_star")["snownlp_score"].mean()
        print("\n=== 用户星级 vs SnowNLP 情感均值 ===")
        print(ag.round(3))

    # 评论长度 vs 情感
    comments["text_len"] = comments["text"].str.len()
    lc = comments["text_len"].corr(comments["snownlp_score"])
    print(f"\n=== 短评字数 与 SnowNLP 情感分数 Pearson 相关: {lc:.4f} ===")

    # 词云
    long_text = " ".join(tok for t in texts[:800] for tok in _jieba_tokens(t))
    if long_text.strip() and WIN_FONT.is_file():
        wc = WordCloud(
            font_path=str(WIN_FONT),
            width=1000,
            height=600,
            background_color="white",
            max_words=200,
            collocations=False,
        ).generate(long_text)
        wc.to_file(str(OUT_DIR / "wordcloud_comments.png"))
        print(f"\n[词云] 已保存 {OUT_DIR / 'wordcloud_comments.png'}")

    # TF-IDF 关键词（全局）
    if len(texts) >= 20:
        vec = TfidfVectorizer(
            max_features=30,
            analyzer=_jieba_tokens,
            token_pattern=None,
        )
        try:
            X = vec.fit_transform(texts)
            sums = np.asarray(X.sum(axis=0)).ravel()
            feats = np.array(vec.get_feature_names_out())
            order = np.argsort(sums)[::-1][:25]
            print("\n=== TF-IDF 权重 Top 词（jieba 分词） ===")
            for w, s in zip(feats[order], sums[order]):
                print(f"  {w}: {s:.3f}")
        except Exception as e:
            print(f"TF-IDF 跳过: {e}")

    # 各情感下的代表性词（简单：各情感子集分别 TF-IDF）
    for label in ["正面", "负面"]:
        sub_texts = comments.loc[comments["sentiment_label"] == label, "text"].tolist()
        if len(sub_texts) < 15:
            continue
        vec = TfidfVectorizer(max_features=15, analyzer=_jieba_tokens, token_pattern=None)
        try:
            X = vec.fit_transform(sub_texts)
            sums = np.asarray(X.sum(axis=0)).ravel()
            feats = np.array(vec.get_feature_names_out())
            order = np.argsort(sums)[::-1][:10]
            print(f"\n=== {label} 短评 TF-IDF Top 词 ===")
            print(", ".join(feats[order]))
        except Exception:
            pass

    # Plotly：情感随时间（按月）
    ts = comments.dropna(subset=["datetime"]).copy()
    if len(ts) > 20:
        ts["month"] = ts["datetime"].dt.to_period("M").dt.to_timestamp()
        g = ts.groupby("month")["snownlp_score"].mean().reset_index()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=g["month"], y=g["snownlp_score"], mode="lines+markers", name="月均情感"))
        fig.update_layout(title="短评 SnowNLP 情感分数月度趋势", yaxis_title="情感 (0~1)", xaxis_title="月份")
        fig.write_html(OUT_DIR / "plotly_sentiment_timeline.html", include_plotlyjs="cdn")


def _sample_comment_texts(
    comments: pd.DataFrame,
    *,
    max_docs: int,
    min_chars: int,
    random_state: int = 42,
) -> list[str]:
    s = comments["text"].astype(str).str.strip()
    s = s[s.str.len() >= min_chars]
    if s.empty:
        return []
    if max_docs > 0 and len(s) > max_docs:
        s = s.sample(n=max_docs, random_state=random_state)
    return s.tolist()


def _lda_topic_top_words(
    lda: LatentDirichletAllocation,
    feature_names: np.ndarray,
    n_words: int = 8,
) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for k in range(lda.n_components):
        weights = lda.components_[k]
        top = np.argsort(weights)[::-1][:n_words]
        out[k] = [str(feature_names[i]) for i in top]
    return out


def run_lda_topics(
    comments: pd.DataFrame,
    *,
    n_topics: int = 10,
    max_docs: int = 8000,
    min_chars: int = 10,
    random_state: int = 42,
) -> None:
    """短评 LDA 主题建模（词袋 + sklearn）。BERTopic 见 analysis/bertopic_movie_comments.py。"""
    texts = _sample_comment_texts(
        comments, max_docs=max_docs, min_chars=min_chars, random_state=random_state
    )
    n_min = max(80, n_topics * 8)
    if len(texts) < n_min:
        print(f"\n[LDA 主题] 有效短评仅 {len(texts)} 条（建议 ≥ {n_min}），跳过。")
        return

    sep = "=" * 60
    print(f"\n{sep}\nLDA 主题建模 | 语料 {len(texts)} 条 | 目标主题数约 {n_topics}\n{sep}")

    t0 = time.perf_counter()
    min_df = max(2, min(5, len(texts) // 200))
    vec = CountVectorizer(
        max_df=0.92,
        min_df=min_df,
        max_features=12000,
        analyzer=_jieba_tokens,
        token_pattern=None,
    )
    try:
        X = vec.fit_transform(texts)
    except ValueError as e:
        print(f"[LDA] 词袋矩阵构造失败: {e}")
        return

    if X.shape[1] < n_topics * 3:
        print(f"[LDA] 有效词项过少（{X.shape[1]}），跳过。")
        return

    lda_n = min(n_topics, X.shape[1] // 3)
    lda_n = max(2, lda_n)
    lda = LatentDirichletAllocation(
        n_components=lda_n,
        max_iter=45,
        learning_method="batch",
        random_state=random_state,
        evaluate_every=-1,
    )
    lda.fit(X)
    lda_time = time.perf_counter() - t0
    names = vec.get_feature_names_out()
    lda_top = _lda_topic_top_words(lda, names, n_words=8)
    lda_perp = float("nan")
    try:
        lda_perp = float(lda.perplexity(X))
    except Exception:
        pass

    doc_topic = lda.transform(X)
    dom = np.asarray(doc_topic.argmax(axis=1)).ravel()
    lda_sizes = pd.Series(dom).value_counts().reindex(range(lda_n), fill_value=0).sort_index()

    print(f"\n--- LDA（词袋共现，n_components={lda_n}）---")
    print(f"拟合耗时: {lda_time:.2f}s | perplexity: {lda_perp:.4f}")
    for k in range(lda_n):
        print(f"  主题{k}: " + " / ".join(lda_top[k]))

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar([str(i) for i in lda_sizes.index], lda_sizes.values.astype(int), color="steelblue", alpha=0.88)
    ax.set_title("LDA：各短评在「概率最大」主题上的归类条数")
    ax.set_xlabel("主题 id")
    ax.set_ylabel("条数")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "topic_lda_doc_counts.png", dpi=150)
    plt.close(fig)
    print(f"\n[LDA] 图表已保存: {OUT_DIR / 'topic_lda_doc_counts.png'}")


def main(
    comment_limit: int | None = None,
    *,
    run_lda_topics_flag: bool = True,
    topic_n: int = 10,
    topic_max_docs: int = 8000,
) -> None:
    csv_path = DATA_DIR / "movie.csv"
    jsonl_path = DATA_DIR / "movie_comments_nlp.jsonl"
    if not csv_path.is_file():
        raise FileNotFoundError(csv_path)

    movies = _load_movies(csv_path)
    run_movie_stats(movies)
    plot_figures_movies(movies)
    plot_plotly_interactive(movies)

    if jsonl_path.is_file():
        comments = _load_comments_jsonl(jsonl_path, limit=comment_limit)
        run_nlp_comments(comments)
        if run_lda_topics_flag and not comments.empty:
            run_lda_topics(
                comments,
                n_topics=topic_n,
                max_docs=topic_max_docs,
            )
    else:
        print(f"未找到短评文件: {jsonl_path}")

    print(f"\n全部图表已写入: {OUT_DIR}")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="豆瓣电影 EDA + 短评 NLP")
    p.add_argument(
        "--comment-limit",
        type=int,
        default=None,
        help="仅处理前 N 条短评（调试用）；默认处理全部",
    )
    p.add_argument(
        "--no-lda-topics",
        action="store_true",
        help="跳过短评 LDA 主题建模（BERTopic 请单独运行 analysis/bertopic_movie_comments.py）",
    )
    p.add_argument(
        "--no-topic-compare",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    p.add_argument(
        "--topic-n",
        type=int,
        default=10,
        help="LDA 主题数目标（组件数上限），默认 10",
    )
    p.add_argument(
        "--topic-max-docs",
        type=int,
        default=8000,
        help="主题建模最多随机抽样短评条数（控制耗时），默认 8000；≤0 表示不抽样",
    )
    args = p.parse_args()
    skip_lda = args.no_lda_topics or args.no_topic_compare
    main(
        comment_limit=args.comment_limit,
        run_lda_topics_flag=not skip_lda,
        topic_n=args.topic_n,
        topic_max_docs=args.topic_max_docs,
    )
