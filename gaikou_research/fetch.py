"""ページの取得と本文テキスト化（キャッシュ付き）。"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .config import Config, Source

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


@dataclass
class FetchResult:
    source_id: str
    url: Optional[str]
    status: str  # ok / cached / error
    http_status: Optional[int] = None
    final_url: Optional[str] = None
    title: str = ""
    chars: int = 0
    error: str = ""


def html_to_text(html: str) -> tuple[str, str]:
    """HTML から (タイトル, 本文テキスト) を取り出す。"""
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.get_text(strip=True) if soup.title else "")[:200]
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "form", "nav", "footer", "header"]):
        tag.decompose()
    lines = []
    for line in soup.get_text("\n").splitlines():
        line = " ".join(line.split())
        if line:
            lines.append(line)
    return title, "\n".join(lines)


def _paths(cfg: Config, source: Source) -> tuple[Path, Path]:
    d = cfg.data_dir()
    return d / "raw" / f"{source.id}.html", d / "text" / f"{source.id}.txt"


def fetch_source(cfg: Config, source: Source, force: bool = False, session: Optional[requests.Session] = None) -> FetchResult:
    raw_path, text_path = _paths(cfg, source)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.parent.mkdir(parents=True, exist_ok=True)

    if text_path.exists() and not force:
        text = text_path.read_text(encoding="utf-8")
        title = text.split("\n", 1)[0].removeprefix("# ")
        return FetchResult(source.id, source.url, "cached", title=title, chars=len(text))

    try:
        if source.file:
            p = Path(source.file)
            if not p.is_absolute():
                p = cfg.base_dir / p
            content = p.read_text(encoding="utf-8")
            if p.suffix.lower() in (".html", ".htm"):
                title, body = html_to_text(content)
            else:
                title, body = p.stem, content
            http_status, final_url = None, str(p)
        else:
            s = session or requests.Session()
            resp = s.get(
                source.url,
                headers={"User-Agent": USER_AGENT, "Accept-Language": "ja,en;q=0.5"},
                timeout=30,
            )
            http_status, final_url = resp.status_code, resp.url
            if resp.status_code != 200:
                return FetchResult(source.id, source.url, "error", http_status, final_url,
                                   error=f"HTTP {resp.status_code}")
            resp.encoding = resp.apparent_encoding if resp.encoding in (None, "ISO-8859-1") else resp.encoding
            raw_path.write_text(resp.text, encoding="utf-8")
            title, body = html_to_text(resp.text)
    except Exception as e:  # ネットワーク・ファイルエラーは記録して続行
        return FetchResult(source.id, source.url, "error", error=f"{type(e).__name__}: {e}")

    text_path.write_text(f"# {title}\n{body}", encoding="utf-8")
    return FetchResult(source.id, source.url, "ok", http_status, final_url, title=title, chars=len(body))


def fetch_all(cfg: Config, force: bool = False, delay: float = 1.0) -> list[FetchResult]:
    results = []
    session = requests.Session()
    for i, src in enumerate(cfg.sources):
        r = fetch_source(cfg, src, force=force, session=session)
        results.append(r)
        print(f"[fetch] {src.id}: {r.status} {r.error or r.title[:50]}")
        if r.status == "ok" and src.url and i < len(cfg.sources) - 1:
            time.sleep(delay)  # 相手サイトに負荷をかけない
    log = cfg.data_dir() / "fetch_log.json"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def load_fetch_log(cfg: Config) -> dict[str, dict]:
    log = cfg.data_dir() / "fetch_log.json"
    if not log.exists():
        return {}
    return {r["source_id"]: r for r in json.loads(log.read_text(encoding="utf-8"))}
