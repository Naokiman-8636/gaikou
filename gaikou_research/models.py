"""Claude に抽出させるデータの型と、集計結果の型。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Claude の構造化出力（1ページ分）
# ---------------------------------------------------------------------------


class Rating(BaseModel):
    platform: str = Field(description="評価の出どころ。例: Google, ホームプロ, リショップナビ, みん評, サイト独自")
    score: Optional[float] = Field(description="点数（5点満点に換算できない場合は null）")
    count: Optional[int] = Field(description="口コミ件数。ページに書かれていなければ null")


class CompanyMention(BaseModel):
    name: str = Field(description="ページに書かれている業者名（店舗名・屋号）")
    legal_name: Optional[str] = Field(description="運営会社の正式名称が書かれていれば")
    location: Optional[str] = Field(description="所在地（市町村・町名まで）")
    menus: list[str] = Field(description="対応している工事メニューの id（指定リストの中からのみ）")
    ratings: list[Rating]
    founded_year: Optional[int] = Field(description="創業・設立の西暦年")
    project_count: Optional[int] = Field(description="施工実績の件数（『○件以上』なら○）")
    strengths: list[str] = Field(description="特徴・強み（ページの記述を短く要約）")
    positive_reviews: list[str] = Field(description="好意的な口コミの要旨")
    negative_reviews: list[str] = Field(description="否定的な口コミ・注意点の要旨")
    price_notes: Optional[str] = Field(description="価格・費用に関する記述")
    warranty: Optional[str] = Field(description="保証に関する記述")
    rank_on_page: Optional[int] = Field(description="ページ内の順位（ランキングでなければ null）")
    evidence_quote: str = Field(description="この業者についてのページ本文からの短い引用（60字以内）")


class PageExtraction(BaseModel):
    page_title: str
    is_pr_or_self_promoted: bool = Field(
        description="PR表記がある、または掲載業者自身・その関連会社が運営していると読み取れる場合 true"
    )
    pr_notes: Optional[str] = Field(description="PR・運営者・掲載順の基準についての注記")
    ranking_basis: Optional[str] = Field(description="ランキングの根拠として書かれていること")
    companies: list[CompanyMention]


# ---------------------------------------------------------------------------
# 集計結果
# ---------------------------------------------------------------------------


class SourceRef(BaseModel):
    source_id: str
    title: str
    url: Optional[str]
    is_pr: bool


class CompanyProfile(BaseModel):
    key: str
    display_name: str
    legal_names: list[str] = []
    locations: list[str] = []
    sources: list[SourceRef] = []
    menu_sources: dict[str, list[str]] = {}
    ratings: list[dict] = []
    founded_year: Optional[int] = None
    project_count: Optional[int] = None
    strengths: list[str] = []
    positive_reviews: list[str] = []
    negative_reviews: list[str] = []
    price_notes: list[str] = []
    warranty: list[str] = []
    # スコアの内訳（0〜1）
    presence: float = 0.0
    rating_score: Optional[float] = None
    rating_bayes: Optional[float] = None
    record_score: Optional[float] = None
    flags: list[str] = []


class MenuRankingEntry(BaseModel):
    company_key: str
    score: float
    breakdown: dict[str, float]
