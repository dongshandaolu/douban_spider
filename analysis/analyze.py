from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

try:
    from snownlp import SnowNLP
except Exception:
    SnowNLP = None

DATA = Path("data/movies.csv")
OUT = Path("output")
OUT.mkdir(exist_ok=True)


def clean_df(df):
    df = df.drop_duplicates(subset=["title"]).copy()
    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    df["vote_count"] = pd.to_numeric(df["vote_count"], errors="coerce").fillna(0).astype(int)
    df["rank_num"] = pd.to_numeric(df["rank_num"], errors="coerce").astype("Int64")
    df["year"] = df["year"].astype(str).str.extract(r"(\d{4})", expand=False)
    return df


def split_genre(df):
    s = df["genre"].fillna("").astype(str).str.split(r"[\/,、; ]+")
    return df.assign(genre_item=s).explode("genre_item")


def plot_basic(df):
    plt.figure()
    df["score"].dropna().hist(bins=15)
    plt.title("评分分布")
    plt.xlabel("score")
    plt.ylabel("count")
    plt.tight_layout()
    plt.savefig(OUT / "score_hist.png", dpi=300)
    plt.close()

    plt.figure()
    top10 = df.nlargest(10, "score")[["title", "score"]].sort_values("score")
    plt.barh(top10["title"], top10["score"])
    plt.title("高分电影Top10")
    plt.tight_layout()
    plt.savefig(OUT / "top10.png", dpi=300)
    plt.close()

    plt.figure()
    plt.scatter(df["vote_count"], df["score"])
    plt.xlabel("vote_count")
    plt.ylabel("score")
    plt.title("评分与评价人数关系")
    plt.tight_layout()
    plt.savefig(OUT / "scatter_votes_score.png", dpi=300)
    plt.close()


def sentiment_stats(df):
    if "intro" not in df.columns:
        return
    texts = df["intro"].dropna().astype(str).tolist()
    if not texts or SnowNLP is None:
        return
    scores = [SnowNLP(t).sentiments for t in texts if len(t.strip()) > 1]
    if not scores:
        return
    pos = sum(s >= 0.6 for s in scores)
    neu = sum(0.4 <= s < 0.6 for s in scores)
    neg = sum(s < 0.4 for s in scores)
    print("情感统计:", {"正面": pos, "中性": neu, "负面": neg})


def main():
    if not DATA.exists():
        raise FileNotFoundError("请先运行 main_requests.py 生成 data/movies.csv")
    df = pd.read_csv(DATA)
    df = clean_df(df)
    df.to_csv(OUT / "clean_movies.csv", index=False, encoding="utf-8-sig")

    print("总数:", len(df))
    print("Top10:")
    print(df.nlargest(10, "score")[["title", "score", "vote_count"]])

    genre_df = split_genre(df)
    genre_count = genre_df["genre_item"].value_counts().head(10)
    plt.figure()
    genre_count.plot(kind="bar")
    plt.title("类型分布Top10")
    plt.tight_layout()
    plt.savefig(OUT / "genre_top10.png", dpi=300)
    plt.close()

    corr = df[["score", "vote_count"]].corr().iloc[0, 1]
    print("评分-评价人数相关系数:", round(float(corr), 4))

    plot_basic(df)
    sentiment_stats(df)


if __name__ == "__main__":
    main()
