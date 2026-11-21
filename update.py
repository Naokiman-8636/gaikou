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
import json
import os
import signal
import subprocess
import sys
import time
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
    ap.add_argument("--timeout", type=int, default=60, help="1医院あたりの制限時間（秒）。超えたら飛ばす")
    ap.add_argument("--worker", help=argparse.SUPPRESS)  # 内部用: 1医院だけ調べてJSONを出力
    args = ap.parse_args()

    clinics = yaml.safe_load(args.clinics.read_text("utf-8"))["clinics"]
    if args.only:
        ids = set(args.only.split(","))
        clinics = [c for c in clinics if c["id"] in ids]

    if args.worker:
        run_worker(args, clinics)
        return

    reviews = ReviewCollector(args.data / "reviews_cache.json")
    entries = []
    try:
        for n, c in enumerate(clinics, 1):
            print(f"({n}/{len(clinics)}) {c['name']} ...", flush=True)
            t0 = time.time()
            st = Status(state="unknown", message="（受付状況は未取得）") if args.no_status \
                else check_in_subprocess(c, args)
            rv = reviews.collect(c, force=args.refresh_reviews)
            entry = {"clinic": c, "status": st.to_dict(), "reviews": rv, **score(c, rv, st.to_dict())}
            entries.append(entry)
            print(f"   [{st.state}] {entry['score']}点 {time.time() - t0:.0f}秒  {st.message}", flush=True)
    finally:
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


def run_worker(args, clinics) -> None:
    """子プロセス側: 1医院の受付状況を調べて JSON を標準出力に書く。"""
    clinic = next(c for c in clinics if c["id"] == args.worker)
    fetcher = Fetcher(render=args.render, delay=args.delay)
    try:
        st = check_clinic(clinic, fetcher)
    finally:
        fetcher.close()
    print("@@RESULT@@" + json.dumps(st.to_dict(), ensure_ascii=False), flush=True)


def check_in_subprocess(clinic: dict, args) -> Status:
    """医院ごとに別プロセスで調べ、制限時間を超えたらブラウザごと強制終了して次へ進む。"""
    cmd = [sys.executable, str(Path(__file__).resolve()), "--worker", clinic["id"],
           "--clinics", str(args.clinics), "--delay", str(args.delay)]
    if args.render:
        cmd.append("--render")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            start_new_session=True)
    try:
        out, err = proc.communicate(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)  # Chromium などの孫プロセスもまとめて終了
        proc.communicate()
        return Status(state="error", message=f"{args.timeout}秒以内に応答がなく打ち切り（受付ページで確認）",
                      source_url=clinic.get("reservation_url") or clinic.get("homepage"))
    for line in out.splitlines():
        if line.startswith("@@RESULT@@"):
            return Status(**json.loads(line[len("@@RESULT@@"):]))
    tail = (err.strip().splitlines() or ["不明なエラー"])[-1][:120]
    return Status(state="error", message=f"取得処理エラー: {tail}")


if __name__ == "__main__":
    main()
