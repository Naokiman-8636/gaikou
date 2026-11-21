#!/usr/bin/env python3
"""盛岡周辺の小児科の受付状況と口コミを取得し、おすすめリストを生成する。

使い方:
  python update.py                 # 全医院を更新して docs/ と data/ に出力
  python update.py --only saito-ped,miura-kids
  python update.py --render        # JSで描画される受付ページ用に Playwright を使う
  python update.py --refresh-reviews  # 口コミキャッシュを無視して再取得
  python update.py --no-status     # 受付状況は取得せず口コミとスコアだけ
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from pediatrics import render
from pediatrics.fetch import Fetcher
from pediatrics.reviews import ReviewCollector
from pediatrics.score import now_rank_key, score
from pediatrics.status import Status, check_clinic

ROOT = Path(__file__).resolve().parent
JST = timezone(timedelta(hours=9))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clinics", default=ROOT / "clinics.yaml", type=Path)
    ap.add_argument("--out", default=ROOT / "docs", type=Path)
    ap.add_argument("--data", default=ROOT / "data", type=Path)
    ap.add_argument("--only", help="カンマ区切りの医院ID")
    ap.add_argument("--render", action="store_true", help="Playwright でJS描画してから読む")
    ap.add_argument("--refresh-reviews", action="store_true")
    ap.add_argument("--no-status", action="store_true")
    ap.add_argument("--delay", type=float, default=1.0, help="リクエスト間隔（秒）")
    args = ap.parse_args()

    clinics = yaml.safe_load(args.clinics.read_text("utf-8"))["clinics"]
    if args.only:
        ids = set(args.only.split(","))
        clinics = [c for c in clinics if c["id"] in ids]

    fetcher = Fetcher(render=args.render, delay=args.delay)
    reviews = ReviewCollector(args.data / "reviews_cache.json", fetcher.session)
    entries = []
    try:
        for c in clinics:
            st = Status(state="unknown", message="（受付状況は未取得）") if args.no_status \
                else check_clinic(c, fetcher)
            rv = reviews.collect(c, force=args.refresh_reviews)
            entry = {"clinic": c, "status": st.to_dict(), "reviews": rv, **score(c, rv, st.to_dict())}
            entries.append(entry)
            print(f"[{st.state:9}] {entry['score']:5.1f}点  {c['name']}  {st.message}")
    finally:
        fetcher.close()
        reviews.save()

    for i, e in enumerate(sorted(entries, key=now_rank_key)):
        e["now_rank"] = i
    entries.sort(key=lambda e: -e["score"])

    generated = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    render.write_json(entries, generated, args.data / "latest.json")
    render.write_json(entries, generated, args.out / "latest.json")  # スマホ画面の「最新にする」用
    render.write_html(entries, generated, args.out / "index.html")
    render.write_markdown(entries, generated, args.out / "ranking.md")
    print(f"\n出力: {args.out / 'index.html'} / {args.out / 'ranking.md'} / {args.data / 'latest.json'}")


if __name__ == "__main__":
    main()
