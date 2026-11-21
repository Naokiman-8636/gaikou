"""口コミ評価の取得。

- Google Maps (Places API New): 環境変数 GOOGLE_MAPS_API_KEY があれば使う
- 口コミサイト (Caloo / EPARK 等): ページ内の JSON-LD aggregateRating か評価表記を読む
- どれも取れなければ clinics.yaml の manual_rating を使う

API や外部サイトへのアクセスを減らすため、結果は data/reviews_cache.json に一定期間キャッシュする。
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

CACHE_TTL = 7 * 24 * 3600  # 口コミは頻繁に変わらないので1週間
PLACES_URL = "https://places.googleapis.com/v1/places:searchText"


def extract_aggregate_rating(html: str) -> tuple[float, int] | None:
    """JSON-LD の aggregateRating、または「評価 3.8 (口コミ 12件)」のような表記から抽出。"""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for item in data if isinstance(data, list) else [data]:
            agg = item.get("aggregateRating") if isinstance(item, dict) else None
            if agg and agg.get("ratingValue"):
                count = agg.get("reviewCount") or agg.get("ratingCount") or 0
                return float(agg["ratingValue"]), int(count)
    text = soup.get_text(" ")
    m = re.search(r"(?:総合)?評価[^0-9]{0,6}([1-5]\.[0-9]{1,2})", text)
    if m:
        c = re.search(r"口コミ[^0-9]{0,6}([0-9]{1,4})\s*件", text) or re.search(r"([0-9]{1,4})\s*件の口コミ", text)
        return float(m.group(1)), int(c.group(1)) if c else 0
    return None


class ReviewCollector:
    def __init__(self, cache_path: Path, session: requests.Session | None = None):
        self.cache_path = cache_path
        self.cache = json.loads(cache_path.read_text("utf-8")) if cache_path.exists() else {}
        self.session = session or requests.Session()
        self.api_key = os.environ.get("GOOGLE_MAPS_API_KEY")

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1), "utf-8")

    def _cached(self, key: str, fn, force: bool):
        hit = self.cache.get(key)
        if hit and not force and time.time() - hit["ts"] < CACHE_TTL:
            return hit["value"]
        try:
            value = fn()
        except Exception as exc:  # noqa: BLE001
            value = {"error": f"{type(exc).__name__}: {exc}"}
        if "error" in value:
            # 失敗はキャッシュせず次回再試行。古い成功結果があればそれを使い続ける
            return hit["value"] if hit else value
        self.cache[key] = {"ts": time.time(), "value": value}
        return value

    def google(self, query: str) -> dict:
        resp = self.session.post(
            PLACES_URL,
            headers={
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": "places.displayName,places.rating,places.userRatingCount,"
                "places.googleMapsUri,places.formattedAddress,places.nationalPhoneNumber,"
                "places.regularOpeningHours.weekdayDescriptions,places.websiteUri",
            },
            json={"textQuery": query, "languageCode": "ja", "regionCode": "JP"},
            timeout=20,
        )
        resp.raise_for_status()
        places = resp.json().get("places") or []
        if not places:
            return {"error": "not found"}
        p = places[0]
        return {
            "source": "Google",
            "name": p.get("displayName", {}).get("text"),
            "rating": p.get("rating"),
            "count": p.get("userRatingCount", 0),
            "url": p.get("googleMapsUri"),
            "address": p.get("formattedAddress"),
            "phone": p.get("nationalPhoneNumber"),
            "website": p.get("websiteUri"),
            "hours": (p.get("regularOpeningHours") or {}).get("weekdayDescriptions"),
        }

    def site(self, url: str, source: str) -> dict:
        resp = self.session.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding
        got = extract_aggregate_rating(resp.text)
        if not got:
            return {"error": "rating not found", "url": url}
        return {"source": source, "rating": got[0], "count": got[1], "url": url}

    def collect(self, clinic: dict, force: bool = False) -> list[dict]:
        out: list[dict] = []
        rv = clinic.get("reviews") or {}
        if self.api_key and rv.get("google_query"):
            out.append(self._cached(f"google:{rv['google_query']}",
                                    lambda: self.google(rv["google_query"]), force))
        for key, label in (("caloo_url", "Caloo"), ("epark_url", "EPARK")):
            if rv.get(key):
                out.append(self._cached(f"site:{rv[key]}", lambda u=rv[key], l=label: self.site(u, l), force))
        if clinic.get("manual_rating"):
            m = dict(clinic["manual_rating"])
            m.setdefault("source", "手入力")
            out.append(m)
        return [r for r in out if r and r.get("rating") is not None]
