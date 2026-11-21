"""結果を JSON / HTML / Markdown に出力する。"""
from __future__ import annotations

import html
import json
from pathlib import Path

STATE_LABEL = {
    "accepting": ("受付中", "ok"),
    "closed": ("受付終了", "closed"),
    "full": ("枠なし", "closed"),
    "unknown": ("要確認", "unknown"),
    "error": ("取得失敗", "error"),
    "no_site": ("HPなし", "unknown"),
}


def write_json(entries: list[dict], generated_at: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"generated_at": generated_at, "clinics": entries},
                               ensure_ascii=False, indent=1), "utf-8")


def write_markdown(entries: list[dict], generated_at: str, path: Path) -> None:
    lines = [f"# 盛岡周辺 小児科おすすめリスト（{generated_at} 更新）", "",
             "| 順位 | 医院 | 地区 | おすすめ度 | 口コミ | 受付状況 | 電話 |",
             "|---|---|---|---|---|---|---|"]
    for i, e in enumerate(entries, 1):
        c, st = e["clinic"], e["status"]
        label = STATE_LABEL.get(st["state"], ("?", ""))[0]
        rating = f"★{e['rating']} ({e['review_count']}件)" if e["rating"] else "—"
        name = f"[{c['name']}]({c['homepage']})" if c.get("homepage") else c["name"]
        lines.append(f"| {i} | {name} | {c['area']} | {e['score']} | {rating} | "
                     f"{label} {st.get('message') or ''} | {c.get('phone') or '—'} |")
    lines += ["", "※ 受付状況は自動取得のため誤りがあり得ます。受診前に各医院のページ・電話で確認してください。"]
    path.write_text("\n".join(lines) + "\n", "utf-8")


def _e(s) -> str:
    return html.escape(str(s)) if s is not None else ""


def write_html(entries: list[dict], generated_at: str, path: Path) -> None:
    rows = []
    for e in entries:
        c, st = e["clinic"], e["status"]
        label, cls = STATE_LABEL.get(st["state"], ("?", "unknown"))
        rating = (f'<span class="star">★{e["rating"]}</span> <small>{e["review_count"]}件</small>'
                  if e["rating"] else '<small class="muted">口コミ未取得</small>')
        srcs = " ".join(
            f'<a href="{_e(r.get("url"))}" target="_blank" rel="noopener">{_e(r.get("source"))}</a>'
            for r in e["reviews"] if r.get("url"))
        links = []
        if c.get("homepage"):
            links.append(f'<a href="{_e(c["homepage"])}" target="_blank" rel="noopener">公式HP</a>')
        if st.get("source_url") and st.get("source_url") != c.get("homepage"):
            links.append(f'<a href="{_e(st["source_url"])}" target="_blank" rel="noopener">受付ページ</a>')
        if c.get("phone"):
            links.append(f'<a href="tel:{_e(c["phone"])}">{_e(c["phone"])}</a>')
        tags = []
        if c.get("pediatric_only"):
            tags.append("小児科専門")
        if c.get("web_reservation"):
            tags.append("Web受付")
        if c.get("saturday"):
            tags.append("土曜")
        breakdown = " / ".join(f"{k} {v}" for k, v in e["breakdown"].items())
        waiting = st.get("waiting")
        rows.append(f"""
<article class="card" data-score="{e['score']}" data-now="{e['now_rank']}"
  data-area="{_e(c['area'].split()[0])}">
  <header>
    <h2>{_e(c['name'])}</h2>
    <span class="badge {cls}">{label}{f' 待ち{waiting}人' if waiting is not None else ''}</span>
  </header>
  <p class="area">{_e(c['area'])}　{''.join(f'<span class="tag">{t}</span>' for t in tags)}</p>
  <p class="status">{_e(st.get('message'))}{f' <small>({_e(st["system"])})</small>' if st.get('system') else ''}</p>
  <div class="meta">
    <div><b class="score">{e['score']}</b><small>点</small> <span title="{_e(breakdown)}" class="muted">内訳</span></div>
    <div>{rating} {srcs}</div>
  </div>
  <p class="links">{' ・ '.join(links)}</p>
  {f'<p class="notes">{_e(c["notes"])}</p>' if c.get('notes') else ''}
</article>""")

    areas = sorted({e["clinic"]["area"].split()[0] for e in entries})
    area_opts = "".join(f'<option value="{_e(a)}">{_e(a)}</option>' for a in areas)
    page = TEMPLATE.replace("{{GENERATED}}", _e(generated_at)).replace(
        "{{ROWS}}", "\n".join(rows)).replace("{{AREAS}}", area_opts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, "utf-8")


TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>盛岡 小児科ナビ</title>
<style>
:root{--bg:#f7f6f2;--card:#fff;--fg:#1f2328;--muted:#6b7075;--line:#e3e1da;
--ok:#1a7f4b;--okbg:#e3f5ea;--closed:#8a8f94;--closedbg:#eceeef;--unk:#8a6100;--unkbg:#fbf1d6;--err:#b42318;--errbg:#fde8e6;--accent:#2f5fb3}
@media (prefers-color-scheme:dark){:root{--bg:#16181b;--card:#1f2226;--fg:#e8e6e1;--muted:#9aa0a6;--line:#30343a;
--okbg:#143424;--ok:#6fd6a0;--closedbg:#2a2d31;--closed:#a5aab0;--unkbg:#3a2f12;--unk:#e8c060;--errbg:#3d1a17;--err:#ff8f84;--accent:#8fb3ff}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:system-ui,-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif;line-height:1.55}
main{max-width:860px;margin:0 auto;padding:20px 16px 48px}
h1{font-size:1.4rem;margin:0 0 4px}
.sub{color:var(--muted);margin:0 0 16px;font-size:.9rem}
.controls{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}
.controls button,.controls select{font:inherit;padding:6px 12px;border:1px solid var(--line);border-radius:999px;background:var(--card);color:var(--fg);cursor:pointer}
.controls button[aria-pressed=true]{background:var(--accent);border-color:var(--accent);color:#fff}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:12px}
.card header{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
.card h2{font-size:1.08rem;margin:0}
.badge{white-space:nowrap;font-size:.8rem;padding:2px 10px;border-radius:999px;font-weight:600}
.badge.ok{background:var(--okbg);color:var(--ok)}.badge.closed{background:var(--closedbg);color:var(--closed)}
.badge.unknown{background:var(--unkbg);color:var(--unk)}.badge.error{background:var(--errbg);color:var(--err)}
.area{margin:4px 0;color:var(--muted);font-size:.88rem}
.tag{display:inline-block;font-size:.75rem;border:1px solid var(--line);border-radius:4px;padding:0 6px;margin-right:4px;color:var(--fg)}
.status{margin:6px 0;font-size:.92rem}
.meta{display:flex;flex-wrap:wrap;gap:16px;align-items:baseline;font-size:.9rem}
.score{font-size:1.3rem;font-variant-numeric:tabular-nums}
.star{color:#d08a00;font-weight:600}
.muted{color:var(--muted)}
.links{margin:6px 0 0;font-size:.9rem}.links a,.meta a{color:var(--accent)}
.notes{margin:6px 0 0;font-size:.82rem;color:var(--muted)}
footer{color:var(--muted);font-size:.8rem;margin-top:24px}
</style>
</head>
<body>
<main>
<h1>盛岡 小児科ナビ</h1>
<p class="sub">盛岡市・滝沢市・矢巾町・紫波町の小児科　最終更新: {{GENERATED}}</p>
<div class="controls">
  <button data-sort="score" aria-pressed="true">おすすめ順</button>
  <button data-sort="now" aria-pressed="false">今行きやすい順</button>
  <select id="area"><option value="">全エリア</option>{{AREAS}}</select>
</div>
<section id="list">
{{ROWS}}
</section>
<footer>
<p>受付状況は各医院のHP・順番受付ページを自動で読み取った結果です。読み取りに失敗したり、表示が古かったりすることがあります。受診前に必ず受付ページか電話で確認してください。</p>
<p>おすすめ度 = 口コミ（ベイズ補正、60点）+ Web順番受付 15 + 小児科専門 10 + 土曜診療 10 + 受付状況確認可 5。口コミは件数が少なく古い投稿も含みます。</p>
<p>夜間・休日は 盛岡市夜間急患診療所（019-654-1080）、こども医療電話相談 #8000。</p>
</footer>
</main>
<script>
const list=document.getElementById('list');
const cards=[...list.querySelectorAll('.card')];
function apply(sort){
  const area=document.getElementById('area').value;
  cards.sort((a,b)=>sort==='now'? (+a.dataset.now)-(+b.dataset.now) : (+b.dataset.score)-(+a.dataset.score));
  cards.forEach(c=>{c.hidden=!!area && c.dataset.area!==area;list.appendChild(c);});
}
let current='score';
document.querySelectorAll('[data-sort]').forEach(b=>b.addEventListener('click',()=>{
  current=b.dataset.sort;
  document.querySelectorAll('[data-sort]').forEach(x=>x.setAttribute('aria-pressed',x===b));
  apply(current);
}));
document.getElementById('area').addEventListener('change',()=>apply(current));
</script>
</body>
</html>
"""
