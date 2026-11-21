"""Command line entry point.

    python -m gaikou_research run     configs/morioka.yaml   # fetch → extract → report in one go
    python -m gaikou_research fetch   configs/morioka.yaml   # fetch the pages only
    python -m gaikou_research extract configs/morioka.yaml   # extraction with Claude only
    python -m gaikou_research report  configs/morioka.yaml   # aggregate and write the report only (no API)
"""

from __future__ import annotations

import argparse
import sys

from .config import load_config
from .extract import extract_all
from .fetch import fetch_all
from .report import write_report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gaikou_research", description="外構工事業者のリサーチとおすすめリスト作成")
    ap.add_argument("command", choices=["run", "fetch", "extract", "report"])
    ap.add_argument("config", help="設定ファイル（例: configs/morioka.yaml）")
    ap.add_argument("--force", action="store_true", help="キャッシュを無視して取得・抽出し直す")
    ap.add_argument("--out", default="reports", help="レポートの出力先フォルダ")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)

    if args.command in ("run", "fetch"):
        fetch_all(cfg, force=args.force)
    if args.command in ("run", "extract"):
        extract_all(cfg, force=args.force)
    if args.command in ("run", "report"):
        path = write_report(cfg, args.out)
        print(f"[report] {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
