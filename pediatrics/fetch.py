"""HTTP取得。静的HTMLは requests、JSで描画されるページは任意で Playwright を使う。"""
from __future__ import annotations

import time
from dataclasses import dataclass

import requests

USER_AGENT = (
    "Mozilla/5.0 (compatible; pediatric-status-checker/1.0; "
    "+personal use, 1 request per page per run)"
)
TIMEOUT = 20


@dataclass
class Page:
    url: str
    final_url: str
    status: int
    html: str
    error: str | None = None


def _decode(resp: requests.Response) -> str:
    # 日本の医院HPは Shift_JIS / EUC-JP が残っているので、ヘッダに charset が無ければ推定する
    if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


class Fetcher:
    def __init__(self, render: bool = False, delay: float = 1.0):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "ja,en;q=0.5"})
        self.render = render
        self.delay = delay
        self._pw = None
        self._browser = None

    def get(self, url: str, render: bool | None = None) -> Page:
        use_render = self.render if render is None else render
        time.sleep(self.delay)  # 相手サーバーに負荷をかけない
        if use_render:
            page = self._get_rendered(url)
            if page.error is None:
                return page
        try:
            resp = self.session.get(url, timeout=TIMEOUT, allow_redirects=True)
            return Page(url, resp.url, resp.status_code, _decode(resp),
                        None if resp.ok else f"HTTP {resp.status_code}")
        except requests.RequestException as exc:
            return Page(url, url, 0, "", f"{type(exc).__name__}: {str(exc)[:80]}")

    def _get_rendered(self, url: str) -> Page:
        try:
            if self._browser is None:
                from playwright.sync_api import sync_playwright

                self._pw = sync_playwright().start()
                self._browser = self._pw.chromium.launch()
            ctx = self._browser.new_context(user_agent=USER_AGENT, locale="ja-JP")
            pg = ctx.new_page()
            resp = pg.goto(url, wait_until="networkidle", timeout=TIMEOUT * 1000)
            # iframe 内の受付状況も拾えるよう、フレームのテキストを連結する
            html = pg.content()
            for frame in pg.frames[1:]:
                try:
                    html += "\n<!-- frame: %s -->\n" % frame.url + frame.content()
                except Exception:  # noqa: BLE001
                    pass
            status = resp.status if resp else 0
            final = pg.url
            ctx.close()
            return Page(url, final, status, html, None)
        except Exception as exc:  # noqa: BLE001
            return Page(url, url, 0, "", f"render failed: {exc}")

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
            self._pw.stop()
