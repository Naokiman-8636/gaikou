"""Tests that run without calling the API (aggregation, scoring, report, and extraction with a stand-in client)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from gaikou_research import extract as extract_mod
from gaikou_research.aggregate import build_profiles, normalize_name, rank_menu, rank_overall
from gaikou_research.config import load_config
from gaikou_research.fetch import html_to_text
from gaikou_research.models import CompanyMention, PageExtraction, Rating
from gaikou_research.report import write_report

ROOT = Path(__file__).resolve().parent.parent


def _company(name, menus, ratings=(), **kw):
    base = dict(legal_name=None, location="盛岡市", founded_year=None, project_count=None, strengths=[],
                positive_reviews=[], negative_reviews=[], price_notes=None, warranty=None, rank_on_page=None,
                evidence_quote="…")
    base.update(kw)
    return CompanyMention(name=name, menus=list(menus), ratings=[Rating(**r) for r in ratings], **base)


@pytest.fixture
def cfg(tmp_path):
    (tmp_path / "configs").mkdir()
    shutil.copy(ROOT / "configs" / "morioka.yaml", tmp_path / "configs" / "morioka.yaml")
    return load_config(tmp_path / "configs" / "morioka.yaml")


@pytest.fixture
def extractions():
    a = PageExtraction(page_title="A", is_pr_or_self_promoted=False, pr_notes=None, ranking_basis=None, companies=[
        _company("ワンガーデン", ["carport", "parking", "newbuild"], [{"platform": "Google", "score": 4.8, "count": 40}],
                 legal_name="有限会社東海エクステリア", founded_year=1997, project_count=1500, strengths=["雪害対策"]),
        _company("陽だまり工房 盛岡支店", ["carport", "fence"], [{"platform": "Google", "score": 4.3, "count": None}],
                 project_count=20000),
        _company("小さな工務店", ["fence"], [{"platform": "Google", "score": 5.0, "count": 1}]),
    ])
    b = PageExtraction(page_title="B", is_pr_or_self_promoted=True, pr_notes="PR表記", ranking_basis=None, companies=[
        _company("東海エクステリア", ["carport", "garden"], []),
        _company("ガーデンプラス盛岡", ["carport", "parking", "fence"], [{"platform": "Google", "score": 4.5, "count": 244}],
                 negative_reviews=["色ムラ"]),
        _company("タウンライフ", ["newbuild"], []),
    ])
    return {"siteA": a, "siteB": b}


def test_normalize_name():
    assert normalize_name("陽だまり工房 盛岡支店", "盛岡市") == "陽だまり工房"
    assert normalize_name("ガーデンプラス盛岡", "盛岡市") == "ガーデンプラス"
    assert normalize_name("有限会社東海エクステリア", "盛岡市") == "東海エクステリア"
    assert normalize_name("ＦＲＥＥ ＣＯＬＯＲＳ", "盛岡市") == "freecolors"
    assert normalize_name("盛岡", "盛岡市") == "盛岡"  # 市名だけなら消さない


def test_aliases_merge_and_exclude(cfg, extractions):
    profiles = build_profiles(cfg, extractions, {"siteA": "https://a", "siteB": "https://b"})
    one = profiles[normalize_name("ワンガーデン", cfg.city)]
    assert {s.source_id for s in one.sources} == {"siteA", "siteB"}
    assert set(one.menu_sources) == {"carport", "parking", "newbuild", "garden"}
    assert one.display_name == "ワンガーデン"
    assert not any("タウンライフ" in p.display_name for p in profiles.values())


def test_bayes_rating_small_sample_is_shrunk(cfg, extractions):
    profiles = build_profiles(cfg, extractions, {})
    tiny = profiles[normalize_name("小さな工務店", cfg.city)]
    gp = profiles[normalize_name("ガーデンプラス", cfg.city)]
    # 5.0 (1 review) should come out below 4.5 (244 reviews)
    assert tiny.rating_bayes < gp.rating_bayes
    assert "掲載が1サイトのみ" in tiny.flags


def test_menu_ranking(cfg, extractions):
    profiles = build_profiles(cfg, extractions, {})
    carport = rank_menu(cfg, profiles, "carport")
    keys = [e.company_key for e in carport]
    assert normalize_name("小さな工務店", cfg.city) not in keys  # does not offer carports
    assert keys[0] == normalize_name("ワンガーデン", cfg.city)
    assert rank_menu(cfg, profiles, "snow") == []
    assert len(rank_overall(cfg, profiles)) == 4


def test_report_written(cfg, extractions):
    ex_dir = cfg.data_dir() / "extracted"
    ex_dir.mkdir(parents=True)
    # Put them in under real source ids
    (ex_dir / "mynavi.json").write_text(extractions["siteA"].model_dump_json(), encoding="utf-8")
    (ex_dir / "exbiz.json").write_text(extractions["siteB"].model_dump_json(), encoding="utf-8")
    path = write_report(cfg, "reports")
    md = path.read_text(encoding="utf-8")
    assert "## 4. 工事メニュー別ランキング" in md
    assert "### カーポート・ガレージ" in md
    assert "ワンガーデン" in md
    assert "対応業者の情報が見つかりませんでした" in md  # snow
    data = json.loads((cfg.data_dir() / "aggregated.json").read_text(encoding="utf-8"))
    assert data["menus"]["carport"]


def test_html_to_text():
    title, body = html_to_text("<html><head><title>T</title><script>x()</script></head>"
                               "<body><nav>menu</nav><h1>見出し</h1><p>本文  です</p></body></html>")
    assert title == "T"
    assert "見出し" in body and "本文 です" in body and "x()" not in body and "menu" not in body


def test_extract_with_fake_client(cfg):
    src = cfg.sources[0]
    text = cfg.data_dir() / "text" / f"{src.id}.txt"
    text.parent.mkdir(parents=True)
    text.write_text("# page\nワンガーデン …", encoding="utf-8")

    parsed = PageExtraction(page_title="page", is_pr_or_self_promoted=False, pr_notes=None, ranking_basis=None,
                            companies=[_company("ワンガーデン", ["carport", "unknown-menu"])])
    calls = {}

    class FakeMessages:
        def parse(self, **kwargs):
            calls.update(kwargs)
            return SimpleNamespace(stop_reason="end_turn", parsed_output=parsed,
                                   usage=SimpleNamespace(input_tokens=10, output_tokens=5))

    client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))
    result = extract_mod.extract_source(cfg, src, client)
    assert result.companies[0].menus == ["carport"]  # menu ids not in the list are dropped
    assert calls["model"] == "claude-opus-5-5"
    assert calls["fallbacks"] == "default"
    assert "<page>" in calls["messages"][0]["content"]
    # The second call reads from the cache (no API call)
    calls.clear()
    assert extract_mod.extract_source(cfg, src, client).companies[0].name == "ワンガーデン"
    assert calls == {}
