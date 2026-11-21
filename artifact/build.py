#!/usr/bin/env python3
"""claude.ai アーティファクト版のページとデータを作る。

  python artifact/build.py
    → artifact/snapshot.json : アーティファクトのデータベース（snapshot/latest）に書き込む内容
    → artifact/page.html     : 公開するページ（snapshot を「保存版」として埋め込み済み）

元データは update.py が出力した data/latest.json。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLINIC_KEYS = ["id", "name", "area", "address", "phone", "homepage",
               "pediatric_only", "saturday", "web_reservation", "notes"]
STATUS_KEYS = ["state", "waiting", "current_number", "next_number", "message", "system", "source_url"]


def slim(latest: dict) -> dict:
    clinics = []
    checked = False
    for e in latest["clinics"]:
        c, st = e["clinic"], e["status"]
        if st.get("state") in ("accepting", "closed", "full", "error") or st.get("source_url"):
            checked = True
        clinics.append({
            **{k: c.get(k) for k in CLINIC_KEYS},
            "status": {k: st.get(k) for k in STATUS_KEYS},
            "score": e["score"], "breakdown": e["breakdown"],
            "rating": e["rating"], "review_count": e["review_count"],
            "reviews": [{k: r.get(k) for k in ("source", "url", "rating", "count")} for r in e["reviews"]],
            "now_rank": e.get("now_rank", 0),
        })
    return {"generated_at": latest["generated_at"], "status_checked": checked, "clinics": clinics}


def main() -> None:
    latest = json.loads((ROOT / "data" / "latest.json").read_text("utf-8"))
    snap = slim(latest)
    here = Path(__file__).resolve().parent
    (here / "snapshot.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1), "utf-8")
    page = (here / "template.html").read_text("utf-8").replace(
        "/*SNAPSHOT*/null", json.dumps(snap, ensure_ascii=False).replace("</", "<\\/"))
    (here / "page.html").write_text(page, "utf-8")
    print(f"{len(snap['clinics'])}院 / {snap['generated_at']} / 受付状況取得済み={snap['status_checked']}")


if __name__ == "__main__":
    main()
