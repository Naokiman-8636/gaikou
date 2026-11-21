"""結果を JSON / HTML / Markdown に出力する。

HTML はスマホ前提（ホーム画面に追加できるPWA）。docs/ 直下に
index.html / latest.json を書き出し、manifest・service worker・アイコンは docs/ に静的に置いてある。
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from urllib.parse import quote

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


def map_url(c: dict) -> str:
    q = f"{c['name']} {c.get('address') or c.get('area') or ''}".strip()
    return "https://www.google.com/maps/search/?api=1&query=" + quote(q)


def _card(e: dict) -> str:
    c, st = e["clinic"], e["status"]
    label, cls = STATE_LABEL.get(st["state"], ("?", "unknown"))
    waiting = st.get("waiting")
    badge = label + (f"・待ち{waiting}人" if waiting is not None else "")

    if e["rating"]:
        rating = f'<span class="star">★{e["rating"]}</span><small>（{e["review_count"]}件）</small>'
    else:
        rating = '<small class="muted">口コミ未取得</small>'
    srcs = " ".join(
        f'<a href="{_e(r.get("url"))}" target="_blank" rel="noopener">{_e(r.get("source"))}</a>'
        for r in e["reviews"] if r.get("url"))

    tags = [t for t, on in (("小児科専門", c.get("pediatric_only")), ("Web受付", c.get("web_reservation")),
                            ("土曜", c.get("saturday"))) if on]

    # スマホで押しやすい大きなボタン
    actions = []
    res = st.get("source_url") if st.get("source_url") != c.get("homepage") else None
    if res:
        actions.append(f'<a class="btn primary" href="{_e(res)}" target="_blank" rel="noopener">受付ページ</a>')
    if c.get("phone"):
        tel = c["phone"].replace("-", "")
        actions.append(f'<a class="btn{"" if res else " primary"}" href="tel:{_e(tel)}">電話する</a>')
    actions.append(f'<a class="btn" href="{_e(map_url(c))}" target="_blank" rel="noopener">地図</a>')
    if c.get("homepage"):
        actions.append(f'<a class="btn" href="{_e(c["homepage"])}" target="_blank" rel="noopener">公式HP</a>')

    breakdown = "".join(f"<li>{_e(k)} <b>{v}</b></li>" for k, v in e["breakdown"].items())
    system = f'（{_e(st["system"])}）' if st.get("system") else ""
    notes = f'<p class="notes">{_e(c["notes"])}</p>' if c.get("notes") else ""
    return f"""
<article class="card" data-score="{e['score']}" data-now="{e['now_rank']}" data-area="{_e(c['area'].split()[0])}"
  data-state="{_e(st['state'])}">
  <div class="top">
    <h2>{_e(c['name'])}</h2>
    <span class="badge {cls}">{_e(badge)}</span>
  </div>
  <p class="area">{_e(c['area'])}</p>
  <p class="tags">{''.join(f'<span class="tag">{t}</span>' for t in tags)}</p>
  <p class="status">{_e(st.get('message'))}{system}</p>
  <div class="meta">
    <span class="score"><b>{e['score']}</b>点</span>
    <span>{rating} {srcs}</span>
  </div>
  <div class="actions">{''.join(actions)}</div>
  <details><summary>点数の内訳・メモ</summary><ul class="bd">{breakdown}</ul>{notes}</details>
</article>"""


def write_html(entries: list[dict], generated_at: str, path: Path) -> None:
    rows = "\n".join(_card(e) for e in entries)
    areas = sorted({e["clinic"]["area"].split()[0] for e in entries})
    area_opts = "".join(f'<option value="{_e(a)}">{_e(a)}</option>' for a in areas)
    page = (TEMPLATE.replace("{{GENERATED}}", _e(generated_at))
            .replace("{{ROWS}}", rows).replace("{{AREAS}}", area_opts))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, "utf-8")


TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>盛岡 小児科ナビ</title>
<meta name="description" content="盛岡周辺の小児科の受付状況と口コミ">
<meta name="theme-color" content="#2f5fb3">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="小児科ナビ">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<style>
:root{--bg:#f7f6f2;--card:#fff;--fg:#1f2328;--muted:#6b7075;--line:#e3e1da;--accent:#2f5fb3;--accentfg:#fff;
--ok:#1a7f4b;--okbg:#e3f5ea;--closed:#6f747a;--closedbg:#eceeef;--unk:#8a6100;--unkbg:#fbf1d6;--err:#b42318;--errbg:#fde8e6}
@media (prefers-color-scheme:dark){:root{--bg:#16181b;--card:#1f2226;--fg:#e8e6e1;--muted:#9aa0a6;--line:#30343a;--accent:#8fb3ff;--accentfg:#0d1b33;
--okbg:#143424;--ok:#6fd6a0;--closedbg:#2a2d31;--closed:#a5aab0;--unkbg:#3a2f12;--unk:#e8c060;--errbg:#3d1a17;--err:#ff8f84}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif;
  padding-bottom:env(safe-area-inset-bottom)}
a{color:var(--accent)}
.bar{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 92%,transparent);backdrop-filter:blur(8px);
  -webkit-backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:calc(10px + env(safe-area-inset-top)) 16px 10px}
.bar-in,main{max-width:720px;margin:0 auto}
.title{display:flex;align-items:center;justify-content:space-between;gap:8px}
h1{font-size:1.15rem;margin:0}
.upd{font-size:.8rem;color:var(--muted)}
.upd.stale{color:var(--err);font-weight:600}
#reload{font:inherit;font-size:.85rem;min-height:36px;padding:0 14px;border-radius:999px;border:1px solid var(--line);background:var(--card);color:var(--fg)}
.controls{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}
.seg{display:flex;border:1px solid var(--line);border-radius:999px;overflow:hidden;flex:none}
.seg button{font:inherit;font-size:.9rem;min-height:40px;padding:0 14px;border:0;background:var(--card);color:var(--fg)}
.seg button[aria-pressed=true]{background:var(--accent);color:var(--accentfg);font-weight:600}
select,#onlyopen+label{font:inherit;font-size:16px;min-height:40px}
select{padding:0 10px;border:1px solid var(--line);border-radius:999px;background:var(--card);color:var(--fg);flex:none}
.chk{display:flex;align-items:center;gap:6px;white-space:nowrap;font-size:.9rem;flex:none;padding:0 4px}
.chk input{width:20px;height:20px}
main{padding:12px 16px 40px}
.notice{background:var(--unkbg);color:var(--unk);border-radius:10px;padding:10px 12px;font-size:.88rem;margin:0 0 12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin-bottom:12px}
.top{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
.card h2{font-size:1.05rem;margin:0;line-height:1.4}
.badge{white-space:nowrap;font-size:.8rem;padding:3px 10px;border-radius:999px;font-weight:700;flex:none}
.badge.ok{background:var(--okbg);color:var(--ok)}.badge.closed{background:var(--closedbg);color:var(--closed)}
.badge.unknown{background:var(--unkbg);color:var(--unk)}.badge.error{background:var(--errbg);color:var(--err)}
.area{margin:2px 0 0;color:var(--muted);font-size:.85rem}
.tags{margin:6px 0 0}.tags:empty{display:none}
.tag{display:inline-block;font-size:.75rem;border:1px solid var(--line);border-radius:4px;padding:0 6px;margin:0 4px 4px 0}
.status{margin:6px 0;font-size:.9rem}.status:empty{display:none}
.meta{display:flex;flex-wrap:wrap;gap:4px 14px;align-items:baseline;font-size:.9rem}
.score b{font-size:1.35rem;font-variant-numeric:tabular-nums}
.star{color:#d08a00;font-weight:700}
.muted{color:var(--muted)}
.actions{display:grid;grid-template-columns:repeat(auto-fit,minmax(90px,1fr));gap:8px;margin-top:12px}
.btn{display:flex;align-items:center;justify-content:center;min-height:44px;border-radius:10px;border:1px solid var(--line);
  text-decoration:none;color:var(--fg);font-weight:600;font-size:.92rem;background:var(--bg)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:var(--accentfg)}
details{margin-top:10px;font-size:.85rem}
summary{color:var(--muted);cursor:pointer;min-height:32px;display:flex;align-items:center}
.bd{margin:4px 0;padding-left:18px}
.notes{margin:4px 0 0;color:var(--muted)}
.empty{text-align:center;color:var(--muted);padding:24px 0}
footer{color:var(--muted);font-size:.8rem;margin-top:24px}
footer .sos{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:8px 0}
</style>
</head>
<body>
<div class="bar"><div class="bar-in">
  <div class="title">
    <div><h1>盛岡 小児科ナビ</h1>
      <div class="upd" id="upd" data-generated="{{GENERATED}}">更新: {{GENERATED}}</div></div>
    <button id="reload" type="button">最新にする</button>
  </div>
  <div class="controls">
    <div class="seg" role="group" aria-label="並び順">
      <button data-sort="score" aria-pressed="true">おすすめ</button>
      <button data-sort="now" aria-pressed="false">今行きやすい</button>
    </div>
    <select id="area" aria-label="エリア"><option value="">全エリア</option>{{AREAS}}</select>
    <label class="chk"><input type="checkbox" id="onlyopen">受付中のみ</label>
  </div>
</div></div>
<main>
<p class="notice" id="notice" hidden></p>
<section id="list">
{{ROWS}}
</section>
<p class="empty" id="empty" hidden>条件に合う医院がありません</p>
<footer>
<p>受付状況は各医院のHP・順番受付ページを自動で読み取った結果です。誤りや遅れがあり得るため、受診前に必ず受付ページか電話で確認してください。</p>
<div class="sos">
  <a class="btn" href="tel:%238000">こども医療電話相談 #8000</a>
  <a class="btn" href="tel:0196541080">盛岡市夜間急患診療所</a>
</div>
<p>おすすめ度 = 口コミ（件数補正、60点）+ Web順番受付 15 + 小児科専門 10 + 土曜診療 10 + 受付状況確認可 5</p>
</footer>
</main>
<script>
const list=document.getElementById('list'),cards=[...list.querySelectorAll('.card')];
const $=id=>document.getElementById(id);
const store={get(k){try{return localStorage.getItem(k)}catch(e){return null}},set(k,v){try{localStorage.setItem(k,v)}catch(e){}}};
let sort=store.get('sort')||'score';
$('area').value=store.get('area')||'';
$('onlyopen').checked=store.get('onlyopen')==='1';
function apply(){
  const area=$('area').value,only=$('onlyopen').checked;
  cards.sort((a,b)=>sort==='now'?(+a.dataset.now)-(+b.dataset.now):(+b.dataset.score)-(+a.dataset.score));
  let shown=0;
  cards.forEach(c=>{const h=(area&&c.dataset.area!==area)||(only&&c.dataset.state!=='accepting');c.hidden=h;if(!h)shown++;list.appendChild(c);});
  $('empty').hidden=shown>0;
  document.querySelectorAll('[data-sort]').forEach(x=>x.setAttribute('aria-pressed',x.dataset.sort===sort));
  store.set('sort',sort);store.set('area',area);store.set('onlyopen',only?'1':'0');
}
document.querySelectorAll('[data-sort]').forEach(b=>b.addEventListener('click',()=>{sort=b.dataset.sort;apply();}));
$('area').addEventListener('change',apply);$('onlyopen').addEventListener('change',apply);
apply();

// 更新時刻を「◯分前」で表示し、診療時間中に古すぎたら警告
const gen=$('upd').dataset.generated, genAt=new Date(gen.replace(' ','T')+':00+09:00');
function ago(){
  const m=Math.round((Date.now()-genAt)/60000);
  const txt=m<1?'たった今':m<60?m+'分前':m<1440?Math.floor(m/60)+'時間前':Math.floor(m/1440)+'日前';
  const jst=new Date(Date.now()+9*3600e3),h=jst.getUTCHours()+jst.getUTCMinutes()/60,d=jst.getUTCDay();
  const open=d!==0&&h>=8.5&&h<18.5, stale=open&&m>75;
  $('upd').textContent='更新: '+txt+'（'+gen.slice(5)+'）';
  $('upd').classList.toggle('stale',stale);
  $('notice').hidden=!stale;
  if(stale)$('notice').textContent='データが'+txt+'のものです。受付状況は変わっている可能性があります。';
}
ago();setInterval(ago,60000);

// 新しいデータがあれば読み込み直す
async function check(manual){
  const btn=$('reload');if(manual){btn.disabled=true;btn.textContent='確認中…';}
  try{
    const r=await fetch('latest.json?t='+Date.now(),{cache:'no-store'});
    const j=await r.json();
    if(j.generated_at!==gen){location.replace(location.pathname+'?v='+encodeURIComponent(j.generated_at));return;}
    if(manual)btn.textContent='最新です';
  }catch(e){if(manual)btn.textContent='オフライン';}
  if(manual)setTimeout(()=>{btn.disabled=false;btn.textContent='最新にする';},1500);
}
$('reload').addEventListener('click',()=>check(true));
document.addEventListener('visibilitychange',()=>{if(!document.hidden)check(false);});
if('serviceWorker' in navigator)navigator.serviceWorker.register('sw.js').catch(()=>{});
</script>
</body>
</html>
"""
