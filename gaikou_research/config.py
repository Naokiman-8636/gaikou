"""YAML 設定ファイルの読み込み。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class Source:
    id: str
    url: Optional[str] = None
    file: Optional[str] = None  # 手動保存したHTML/テキスト（サイトが読めないとき用）
    note: str = ""


@dataclass
class Menu:
    id: str
    label: str
    description: str = ""


@dataclass
class Weights:
    presence: float = 0.25
    rating: float = 0.35
    record: float = 0.20
    menu_fit: float = 0.20
    negative_penalty: float = 0.03  # 否定的な口コミ1件あたりの減点
    negative_penalty_max: float = 0.10
    pr_source_weight: float = 0.5  # PR記事での掲載は何件分として数えるか


@dataclass
class RatingPrior:
    mean: float = 4.0  # 口コミが少ない業者はこの値に引き寄せる
    weight: int = 10  # 「この件数分の平均的な口コミがある」とみなす
    unknown_count: int = 3  # 件数不明の評価を何件として扱うか


@dataclass
class Config:
    city: str
    prefecture: str
    slug: str
    sources: list[Source]
    menus: list[Menu]
    aliases: dict[str, list[str]] = field(default_factory=dict)
    exclude: list[str] = field(default_factory=list)
    weights: Weights = field(default_factory=Weights)
    rating_prior: RatingPrior = field(default_factory=RatingPrior)
    top_n: int = 5
    model: str = "claude-opus-5-5"
    effort: str = "medium"
    base_dir: Path = Path(".")

    @property
    def menu_ids(self) -> list[str]:
        return [m.id for m in self.menus]

    def data_dir(self) -> Path:
        return self.base_dir / "data" / self.slug


def _slugify(text: str) -> str:
    s = re.sub(r"[^0-9A-Za-z_-]+", "-", text).strip("-").lower()
    return s or "city"


def load_config(path: str | Path) -> Config:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    sources = []
    for i, s in enumerate(raw.get("sources", [])):
        if isinstance(s, str):
            s = {"url": s}
        sid = s.get("id") or f"src{i + 1:02d}"
        if not (s.get("url") or s.get("file")):
            raise ValueError(f"source {sid}: url か file のどちらかが必要です")
        sources.append(Source(id=sid, url=s.get("url"), file=s.get("file"), note=s.get("note", "")))

    ids = [s.id for s in sources]
    if len(ids) != len(set(ids)):
        raise ValueError("source の id が重複しています")

    menus = [Menu(id=m["id"], label=m["label"], description=m.get("description", "")) for m in raw["menus"]]

    cfg = Config(
        city=raw["city"],
        prefecture=raw.get("prefecture", ""),
        slug=raw.get("slug") or _slugify(path.stem),
        sources=sources,
        menus=menus,
        aliases=raw.get("aliases", {}) or {},
        exclude=raw.get("exclude", []) or [],
        weights=Weights(**(raw.get("weights") or {})),
        rating_prior=RatingPrior(**(raw.get("rating_prior") or {})),
        top_n=raw.get("top_n", 5),
        model=raw.get("model", "claude-opus-5-5"),
        effort=raw.get("effort", "medium"),
        base_dir=path.resolve().parent.parent if path.resolve().parent.name == "configs" else Path.cwd(),
    )
    return cfg
