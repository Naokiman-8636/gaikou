"""おすすめ度スコア（100点満点）。

口コミは件数が少ないと極端な値になりやすいので、ベイズ平均（事前平均 PRIOR_MEAN を
PRIOR_WEIGHT 件分混ぜる）で補正してから点数化する。

  口コミ        最大 60点  (補正後の星1〜5 を 0〜60 に線形変換)
  Web順番受付    15点   (3歳児連れで院内の待ち時間を減らせる)
  小児科専門      10点
  土曜診療        10点
  受付状況が自動取得できる  5点
"""
from __future__ import annotations

PRIOR_MEAN = 3.5
PRIOR_WEIGHT = 10


def combined_rating(reviews: list[dict]) -> tuple[float | None, int]:
    total = sum(int(r.get("count") or 0) for r in reviews)
    if not reviews:
        return None, 0
    weighted = sum(float(r["rating"]) * max(int(r.get("count") or 0), 1) for r in reviews)
    n = sum(max(int(r.get("count") or 0), 1) for r in reviews)
    bayes = (PRIOR_MEAN * PRIOR_WEIGHT + weighted) / (PRIOR_WEIGHT + n)
    return round(bayes, 2), total


def score(clinic: dict, reviews: list[dict], status: dict) -> dict:
    rating, count = combined_rating(reviews)
    breakdown = {}
    breakdown["口コミ"] = round(((rating if rating is not None else PRIOR_MEAN) - 1) / 4 * 60, 1)
    breakdown["Web順番受付"] = 15 if clinic.get("web_reservation") else 0
    breakdown["小児科専門"] = 10 if clinic.get("pediatric_only") else 0
    breakdown["土曜診療"] = 10 if clinic.get("saturday") else 0
    breakdown["状況確認可"] = 5 if status.get("state") in ("accepting", "closed", "full") else 0
    return {
        "score": round(sum(breakdown.values()), 1),
        "breakdown": breakdown,
        "rating": rating,
        "review_count": count,
        "rating_is_estimate": rating is None,
    }


STATE_ORDER = {"accepting": 0, "unknown": 1, "no_site": 2, "error": 3, "full": 4, "closed": 5}


def now_rank_key(entry: dict):
    """「今すぐ行きやすい順」: 受付中 → 待ち人数が少ない → おすすめ度。"""
    st = entry["status"]
    waiting = st.get("waiting")
    return (STATE_ORDER.get(st.get("state"), 9), waiting if waiting is not None else 999, -entry["score"])
