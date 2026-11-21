"""複数ページの抽出結果を業者ごとにまとめ、工事メニュー別にスコアを付ける。"""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import date

from .config import Config
from .models import CompanyProfile, MenuRankingEntry, PageExtraction, SourceRef

_CORP_WORDS = r"(株式会社|有限会社|合同会社|合資会社|\(株\)|\(有\)|㈱|㈲)"
_BRANCH_WORDS = r"(本店|本社|支店|営業所|店|ショールーム|展示場)"


def normalize_name(name: str, city: str = "") -> str:
    s = unicodedata.normalize("NFKC", name)
    s = re.sub(_CORP_WORDS, "", s)
    s = re.sub(r"[\s・･/／\-‐–—_.,、。「」『』()（）]", "", s)
    s = s.lower()
    # 「○○ 盛岡支店」「○○盛岡店」「○○盛岡」のような、末尾の市名＋支店表記を外す
    if city:
        city_core = re.sub(r"(市|町|村|区)$", "", unicodedata.normalize("NFKC", city)).lower()
        stripped = re.sub(rf"{re.escape(city_core)}(市)?{_BRANCH_WORDS}?$", "", s)
        if stripped:
            s = stripped
    return s


class NameResolver:
    """表記ゆれを吸収して、業者を同じキーにまとめる。"""

    def __init__(self, cfg: Config):
        self.city = cfg.city
        self.map: dict[str, str] = {}
        self.display: dict[str, str] = {}
        for canonical, aliases in cfg.aliases.items():
            key = normalize_name(canonical, self.city)
            self.display[key] = canonical
            for a in [canonical, *(aliases or [])]:
                self.map[normalize_name(a, self.city)] = key
        self.excluded = {normalize_name(x, self.city) for x in cfg.exclude}

    def resolve(self, name: str, legal_name: str | None = None) -> str:
        for cand in (name, legal_name):
            if cand:
                n = normalize_name(cand, self.city)
                if n in self.map:
                    return self.map[n]
        return normalize_name(name, self.city)

    def is_excluded(self, key: str) -> bool:
        return key in self.excluded


def _bayes_rating(ratings: list[dict], cfg: Config) -> float | None:
    scored = [r for r in ratings if r.get("score") is not None and 0 < r["score"] <= 5]
    if not scored:
        return None
    # 同じ評価サイトの重複掲載は、件数の多い1件だけ使う
    best: dict[str, dict] = {}
    for r in scored:
        plat = r["platform"].lower()
        if plat == "サイト独自":
            continue
        cur = best.get(plat)
        if cur is None or (r.get("count") or 0) > (cur.get("count") or 0):
            best[plat] = r
    if not best:
        return None
    p = cfg.rating_prior
    total_n = sum(r.get("count") or p.unknown_count for r in best.values())
    total = sum(r["score"] * (r.get("count") or p.unknown_count) for r in best.values())
    return (p.mean * p.weight + total) / (p.weight + total_n)


def _record_score(project_count: int | None, founded_year: int | None) -> float | None:
    parts = []
    if project_count and project_count > 0:
        parts.append(min(1.0, math.log10(project_count) / math.log10(20000)))
    if founded_year and 1800 < founded_year <= date.today().year:
        parts.append(min(1.0, (date.today().year - founded_year) / 50))
    return max(parts) if parts else None


def _add_unique(lst: list, items) -> None:
    for x in items:
        if x and x not in lst:
            lst.append(x)


def build_profiles(cfg: Config, extractions: dict[str, PageExtraction],
                   source_urls: dict[str, str | None]) -> dict[str, CompanyProfile]:
    resolver = NameResolver(cfg)
    profiles: dict[str, CompanyProfile] = {}

    for sid, page in extractions.items():
        ref = SourceRef(source_id=sid, title=page.page_title, url=source_urls.get(sid),
                        is_pr=page.is_pr_or_self_promoted)
        for c in page.companies:
            key = resolver.resolve(c.name, c.legal_name)
            if not key or resolver.is_excluded(key):
                continue
            p = profiles.get(key)
            if p is None:
                p = CompanyProfile(key=key, display_name=resolver.display.get(key, c.name))
                profiles[key] = p
            if all(s.source_id != sid for s in p.sources):
                p.sources.append(ref)
            _add_unique(p.legal_names, [c.legal_name])
            _add_unique(p.locations, [c.location])
            for m in c.menus:
                lst = p.menu_sources.setdefault(m, [])
                if sid not in lst:
                    lst.append(sid)
            for r in c.ratings:
                p.ratings.append({**r.model_dump(), "source_id": sid})
            if c.founded_year and (p.founded_year is None or c.founded_year < p.founded_year):
                p.founded_year = c.founded_year
            if c.project_count and (p.project_count is None or c.project_count > p.project_count):
                p.project_count = c.project_count
            _add_unique(p.strengths, c.strengths)
            _add_unique(p.positive_reviews, c.positive_reviews)
            _add_unique(p.negative_reviews, c.negative_reviews)
            _add_unique(p.price_notes, [c.price_notes])
            _add_unique(p.warranty, [c.warranty])

    w = cfg.weights
    weighted = {k: sum(w.pr_source_weight if s.is_pr else 1.0 for s in p.sources) for k, p in profiles.items()}
    max_w = max(weighted.values(), default=1.0) or 1.0
    for k, p in profiles.items():
        p.presence = weighted[k] / max_w
        p.rating_bayes = _bayes_rating(p.ratings, cfg)
        if p.rating_bayes is not None:
            p.rating_score = max(0.0, min(1.0, (p.rating_bayes - 3.5) / 1.5))
        p.record_score = _record_score(p.project_count, p.founded_year)
        if len(p.sources) == 1:
            p.flags.append("掲載が1サイトのみ")
        if p.sources and all(s.is_pr for s in p.sources):
            p.flags.append("PR記事でのみ掲載")
        if p.rating_bayes is None:
            p.flags.append("口コミ点数の情報なし")
        if p.negative_reviews:
            p.flags.append(f"否定的な口コミ・注意点 {len(p.negative_reviews)}件")
    return profiles


def rank_menu(cfg: Config, profiles: dict[str, CompanyProfile], menu_id: str) -> list[MenuRankingEntry]:
    w = cfg.weights
    entries = []
    for k, p in profiles.items():
        menu_srcs = p.menu_sources.get(menu_id, [])
        if not menu_srcs:
            continue
        menu_fit = len(menu_srcs) / max(1, len(p.sources))
        rating = p.rating_score if p.rating_score is not None else 0.4  # 情報なしはやや低めに
        record = p.record_score if p.record_score is not None else 0.3
        penalty = min(w.negative_penalty_max, w.negative_penalty * len(p.negative_reviews))
        breakdown = {
            "presence": w.presence * p.presence,
            "rating": w.rating * rating,
            "record": w.record * record,
            "menu_fit": w.menu_fit * menu_fit,
            "penalty": -penalty,
        }
        entries.append(MenuRankingEntry(company_key=k, score=round(sum(breakdown.values()), 4),
                                        breakdown={a: round(b, 4) for a, b in breakdown.items()}))
    entries.sort(key=lambda e: (-e.score, e.company_key))
    return entries


def rank_overall(cfg: Config, profiles: dict[str, CompanyProfile]) -> list[MenuRankingEntry]:
    """メニューを問わない総合スコア（menu_fit の代わりに対応メニューの幅を使う）。"""
    w = cfg.weights
    n_menus = max(1, len(cfg.menus))
    entries = []
    for k, p in profiles.items():
        breadth = len(p.menu_sources) / n_menus
        rating = p.rating_score if p.rating_score is not None else 0.4
        record = p.record_score if p.record_score is not None else 0.3
        penalty = min(w.negative_penalty_max, w.negative_penalty * len(p.negative_reviews))
        breakdown = {
            "presence": w.presence * p.presence,
            "rating": w.rating * rating,
            "record": w.record * record,
            "menu_fit": w.menu_fit * breadth,
            "penalty": -penalty,
        }
        entries.append(MenuRankingEntry(company_key=k, score=round(sum(breakdown.values()), 4),
                                        breakdown={a: round(b, 4) for a, b in breakdown.items()}))
    entries.sort(key=lambda e: (-e.score, e.company_key))
    return entries
