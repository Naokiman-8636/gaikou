"""予約システムの検出と、受付状況（混み具合）の抽出。

医院ごとに使っている順番受付システムが違うため、
1. HP内のリンク/iframe から予約システムを検出し
2. 予約ページのテキストから「待ち人数」「呼出番号」「受付終了」などを正規表現で拾う
という汎用方式にしている。特定システム向けの抽出は SYSTEM_PARSERS に追加できる。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

# ドメイン/パスの一部 → システム名
KNOWN_SYSTEMS: list[tuple[str, str]] = [
    ("doctorqube.com", "ドクターキューブ"),
    ("atlink.jp", "アットリンク"),
    ("i-ticket", "アイチケット"),
    ("epark.jp", "EPARK"),
    ("fdoc.jp", "EPARK"),
    ("airwait.jp", "Airウェイト"),
    ("medical-net.jp", "メディカルネット"),
    ("mrso.jp", "MRSO"),
    ("melp.life", "メルプ"),
    ("3s-kanri", "順番待ちシステム"),
    ("junban", "順番受付システム"),
    ("jyunban", "順番受付システム"),
    ("junbanmachi", "順番受付システム"),
    ("yoyaku", "Web予約"),
    ("reserve", "Web予約"),
    ("lin.ee", "LINE予約"),
    ("line.me", "LINE予約"),
]

LINK_TEXT_RE = re.compile(r"(順番|受付|予約|WEB受付|ネット受付|待ち状況|呼出|混雑)", re.I)


@dataclass
class Status:
    state: str = "unknown"  # accepting / closed / full / unknown / error / no_site
    waiting: int | None = None  # 待ち人数
    current_number: int | None = None  # 現在の呼出番号
    next_number: int | None = None  # 次に取れる番号
    message: str = ""
    system: str | None = None
    source_url: str | None = None
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def normalize(text: str) -> str:
    """全角数字・全角記号を半角にし、空白を詰める。"""
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text)


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return normalize(soup.get_text(" "))


def identify_system(url: str) -> str | None:
    low = url.lower()
    for key, name in KNOWN_SYSTEMS:
        if key in low:
            return name
    return None


def find_reservation_links(html: str, base_url: str) -> list[tuple[str, str | None]]:
    """HPから予約/順番受付ページの候補URLを返す。[(url, システム名)]。既知システムを優先。"""
    soup = BeautifulSoup(html, "html.parser")
    base_host = urlparse(base_url).netloc
    known: list[tuple[str, str | None]] = []
    generic: list[tuple[str, str | None]] = []
    seen: set[str] = set()

    candidates = [(a.get("href"), a.get_text(" ", strip=True)) for a in soup.find_all("a")]
    candidates += [(f.get("src"), "iframe") for f in soup.find_all("iframe")]
    for href, text in candidates:
        if not href or href.startswith(("tel:", "mailto:", "#", "javascript:")):
            continue
        url = urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)
        system = identify_system(url)
        text = normalize(text or "")
        if system and urlparse(url).netloc != base_host:
            known.append((url, system))
        elif system or LINK_TEXT_RE.search(text):
            generic.append((url, system))
    return known + generic


# ---- 受付状況の抽出 --------------------------------------------------------

NUM = r"([0-9]{1,4})"
WAITING_PATTERNS = [
    rf"(?:待ち人数|お待ちの方|待ち人|順番待ち|待ち)[^0-9]{{0,8}}{NUM}\s*(?:人|名|組)",
    rf"{NUM}\s*(?:人|名|組)\s*(?:待ち|がお待ち)",
]
CURRENT_PATTERNS = [
    rf"(?:現在の?|ただいまの?|診察中の?)(?:呼出|呼び出し|診察|受付)?(?:中の?)?(?:番号|順番)?[^0-9]{{0,6}}{NUM}\s*番",
    rf"(?:呼出|呼び出し)(?:中)?(?:番号)?[^0-9]{{0,6}}{NUM}\s*番",
]
NEXT_PATTERNS = [
    rf"次に(?:お)?(?:取れる|とれる|お取りできる|発券される)(?:番号|順番)?[^0-9]{{0,6}}{NUM}",
    rf"(?:発券|受付)(?:済み?)?(?:番号|数)?[^0-9]{{0,4}}{NUM}\s*番まで",
]
CLOSED_RE = re.compile(
    r"(本日の(?:受付|順番受付|web受付|ネット受付)は終了|受付(?:を)?終了(?:しました|いたしました)?|"
    r"受付時間外|ただいま受付(?:を)?(?:停止|休止)|本日(?:は)?休診|受付停止中)",
    re.I,
)
FULL_RE = re.compile(r"(上限に達し|予約枠(?:が|は)?(?:ありません|満)|満了|満員|定員に達し|空きがありません)")
OPEN_RE = re.compile(r"(受付中|受付しています|受付しております|ただいま受付|発券中|予約可能|空きあり)")


def _first_int(patterns: list[str], text: str) -> int | None:
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return int(m.group(1))
    return None


def parse_status_text(text: str) -> Status:
    """予約ページのテキストから受付状況を推定する。"""
    text = normalize(text)
    st = Status()
    st.waiting = _first_int(WAITING_PATTERNS, text)
    st.current_number = _first_int(CURRENT_PATTERNS, text)
    st.next_number = _first_int(NEXT_PATTERNS, text)
    if st.waiting is None and st.current_number is not None and st.next_number is not None:
        st.waiting = max(st.next_number - st.current_number - 1, 0)

    for rx, label in ((CLOSED_RE, "closed"), (FULL_RE, "full"), (OPEN_RE, "accepting")):
        m = rx.search(text)
        if m:
            st.state = label
            st.details.append(m.group(0))
            break
    if st.state == "unknown" and (st.waiting is not None or st.current_number is not None):
        st.state = "accepting"

    parts = []
    if st.current_number is not None:
        parts.append(f"呼出 {st.current_number}番")
    if st.waiting is not None:
        parts.append(f"待ち {st.waiting}人")
    if st.next_number is not None:
        parts.append(f"次の番号 {st.next_number}")
    if st.details:
        parts.append(st.details[0])
    st.message = " / ".join(parts)
    return st


def parse_status_html(html: str) -> Status:
    return parse_status_text(html_to_text(html))


def _readable(st: Status) -> bool:
    return st.state != "unknown" or st.waiting is not None or st.current_number is not None


def check_clinic(clinic: dict, fetcher) -> Status:
    """1医院ぶんの受付状況を取得する。

    まず普通にHTMLを取得し、読み取れなかったときだけ（--render 指定時）ブラウザで描画し直す。
    """
    res_url = clinic.get("reservation_url")
    home = clinic.get("homepage")
    if not res_url and not home:
        return Status(state="no_site", message="公式HP未登録（電話で確認）")

    system = identify_system(res_url) if res_url else None
    if not res_url:
        page = fetcher.get(home)
        if page.error:
            return Status(state="error", message=f"HP取得失敗: {page.error}", source_url=home)
        links = find_reservation_links(page.html, page.final_url)
        if not links and getattr(fetcher, "render", False):
            rendered = fetcher.get(home, render=True)
            if not rendered.error:
                page = rendered
                links = find_reservation_links(page.html, page.final_url)
        if not links:
            # HP自体に受付状況が直接書かれているケースもある
            st = parse_status_html(page.html)
            if st.waiting is not None or st.current_number is not None:
                st.source_url = page.final_url
                return st
            return Status(state="unknown", message="HPに予約/順番受付ページが見つかりません",
                          source_url=page.final_url)
        res_url, system = links[0]

    page = fetcher.get(res_url)
    st = parse_status_html(page.html) if not page.error else Status()
    if not _readable(st) and getattr(fetcher, "render", False):
        rendered = fetcher.get(res_url, render=True)
        if not rendered.error:
            page = rendered
            st = parse_status_html(page.html)
    if page.error:
        return Status(state="error", message=f"予約ページ取得失敗: {page.error}",
                      system=system, source_url=res_url)
    st.system = system or identify_system(page.final_url)
    st.source_url = page.final_url
    if not st.message:
        st.message = "受付状況を自動で読み取れません（予約ページで確認）"
    return st
