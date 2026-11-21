"""Write the aggregated results as a Markdown report."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .aggregate import build_profiles, rank_menu, rank_overall
from .config import Config
from .extract import load_extractions
from .fetch import load_fetch_log
from .models import CompanyProfile, MenuRankingEntry


def _fmt_ratings(p: CompanyProfile) -> str:
    parts = []
    seen = set()
    for r in p.ratings:
        if r.get("score") is None:
            continue
        label = f"{r['platform']} {r['score']:g}" + (f"（{r['count']}件）" if r.get("count") else "（件数不明）")
        if label not in seen:
            seen.add(label)
            parts.append(label)
    return "、".join(parts) if parts else "—"


def _fmt_record(p: CompanyProfile) -> str:
    parts = []
    if p.founded_year:
        parts.append(f"{p.founded_year}年創業")
    if p.project_count:
        parts.append(f"実績{p.project_count:,}件以上")
    return "、".join(parts) if parts else "—"


def _src_links(p: CompanyProfile, ids: list[str] | None = None) -> str:
    srcs = [s for s in p.sources if ids is None or s.source_id in ids]
    return " ".join(f"[{s.source_id}{'※PR' if s.is_pr else ''}]({s.url})" if s.url else f"{s.source_id}" for s in srcs)


def _table_escape(s: str) -> str:
    return s.replace("|", "／").replace("\n", " ")


def _ranking_table(cfg: Config, profiles: dict[str, CompanyProfile], entries: list[MenuRankingEntry],
                   menu_id: str | None) -> list[str]:
    lines = ["| 順位 | 業者 | スコア | 内訳（掲載/口コミ/実績/適合/減点） | 根拠 | 注意 |",
             "|---|---|---|---|---|---|"]
    for i, e in enumerate(entries[: cfg.top_n], 1):
        p = profiles[e.company_key]
        b = e.breakdown
        detail = f"{b['presence']:.2f}/{b['rating']:.2f}/{b['record']:.2f}/{b['menu_fit']:.2f}/{b['penalty']:.2f}"
        reason = "；".join(p.strengths[:2]) or "—"
        ids = p.menu_sources.get(menu_id) if menu_id else None
        lines.append(
            f"| {i} | **{_table_escape(p.display_name)}** | {e.score:.2f} | {detail} | "
            f"{_table_escape(reason)}（{_src_links(p, ids)}） | {_table_escape('、'.join(p.flags)) or '—'} |"
        )
    return lines


def build_report(cfg: Config) -> tuple[str, dict]:
    extractions = load_extractions(cfg)
    fetch_log = load_fetch_log(cfg)
    urls = {s.id: s.url for s in cfg.sources}
    profiles = build_profiles(cfg, extractions, urls)

    menu_rankings = {m.id: rank_menu(cfg, profiles, m.id) for m in cfg.menus}
    overall = rank_overall(cfg, profiles)
    w = cfg.weights

    L: list[str] = []
    L += [f"# {cfg.prefecture}{cfg.city} 外構工事業者 おすすめリスト（自動生成）", "",
          f"生成日: {date.today().isoformat()}　／　抽出モデル: {cfg.model}", ""]

    L += ["## 1. 読み込んだ情報源", "", "| id | ページ | 取得 | 掲載業者数 | PR・自社運営 | 備考 |", "|---|---|---|---|---|---|"]
    for s in cfg.sources:
        ex = extractions.get(s.id)
        log = fetch_log.get(s.id, {})
        status = log.get("status", "—")
        if status == "error":
            status = f"失敗（{log.get('error', '')}）"
        title = ex.page_title if ex else (log.get("title") or "")
        link = f"[{_table_escape(title or s.url or s.file)}]({s.url})" if s.url else _table_escape(title or s.file)
        pr = ("あり：" + _table_escape(ex.pr_notes or "")) if ex and ex.is_pr_or_self_promoted else ("なし" if ex else "—")
        L.append(f"| {s.id} | {link} | {status} | {len(ex.companies) if ex else '—'} | {pr} | {_table_escape(s.note) or '—'} |")
    L.append("")

    L += ["## 2. 採点方法", "",
          "各ページから業者情報を抜き出し、表記ゆれをまとめたうえで、次の4項目で採点しています（満点1.00）。", "",
          f"- **掲載**（重み {w.presence}）：何サイトに載っているか。PR・自社運営の記事は {w.pr_source_weight} 件分として数える",
          f"- **口コミ**（重み {w.rating}）：評価サイトの点数を件数で重み付けし、件数が少ないほど {cfg.rating_prior.mean} 点に寄せた値"
          f"（件数不明は {cfg.rating_prior.unknown_count} 件扱い）。3.5点→0、5.0点→満点。情報がなければ0.4",
          f"- **実績**（重み {w.record}）：施工件数（2万件で満点）または創業からの年数（50年で満点）。情報がなければ0.3",
          f"- **適合**（重み {w.menu_fit}）：その工事メニューに対応していると書いたサイトの割合",
          f"- **減点**：否定的な口コミ・注意点1件につき {w.negative_penalty}（最大 {w.negative_penalty_max}）", "",
          "> 数値はページに書かれていた内容をそのまま使っています。点数や件数は掲載時点のもので、最新とは限りません。"
          "依頼前に Google マップなどで最新の評価を確認してください。", ""]

    L += ["## 3. 総合ランキング", ""]
    L += _ranking_table(cfg, profiles, overall, None)
    L.append("")

    L += ["## 4. 工事メニュー別ランキング", ""]
    for m in cfg.menus:
        L += [f"### {m.label}", ""]
        entries = menu_rankings[m.id]
        if not entries:
            L += ["対応業者の情報が見つかりませんでした。", ""]
            continue
        L += _ranking_table(cfg, profiles, entries, m.id)
        L.append("")

    L += ["## 5. 業者プロフィール", "",
          "| 業者 | 所在地 | 対応メニュー | 口コミ | 実績 | 掲載サイト |", "|---|---|---|---|---|---|"]
    labels = {m.id: m.label for m in cfg.menus}
    for e in overall:
        p = profiles[e.company_key]
        menus = "、".join(labels[m] for m in cfg.menu_ids if m in p.menu_sources) or "—"
        name = p.display_name + (f"（{'／'.join(p.legal_names)}）" if p.legal_names else "")
        L.append(f"| {_table_escape(name)} | {_table_escape('／'.join(p.locations)) or '—'} | {menus} | "
                 f"{_table_escape(_fmt_ratings(p))} | {_fmt_record(p)} | {_src_links(p)} |")
    L.append("")

    L += ["## 6. 口コミ・注意点の詳細", ""]
    for e in overall:
        p = profiles[e.company_key]
        if not (p.positive_reviews or p.negative_reviews or p.price_notes or p.warranty):
            continue
        L += [f"### {p.display_name}", ""]
        for x in p.positive_reviews[:4]:
            L.append(f"- 👍 {x}")
        for x in p.negative_reviews[:4]:
            L.append(f"- ⚠️ {x}")
        for x in p.price_notes[:2]:
            L.append(f"- 💴 {x}")
        for x in p.warranty[:2]:
            L.append(f"- 🛡️ {x}")
        L.append("")

    data = {
        "city": cfg.city,
        "generated": date.today().isoformat(),
        "profiles": {k: p.model_dump() for k, p in profiles.items()},
        "overall": [e.model_dump() for e in overall],
        "menus": {k: [e.model_dump() for e in v] for k, v in menu_rankings.items()},
    }
    return "\n".join(L), data


def write_report(cfg: Config, out_dir: str | Path = "reports") -> Path:
    md, data = build_report(cfg)
    out = Path(out_dir)
    if not out.is_absolute():
        out = cfg.base_dir / out
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / f"{cfg.slug}-{date.today().isoformat()}.md"
    md_path.write_text(md, encoding="utf-8")
    (cfg.data_dir() / "aggregated.json").parent.mkdir(parents=True, exist_ok=True)
    (cfg.data_dir() / "aggregated.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path
