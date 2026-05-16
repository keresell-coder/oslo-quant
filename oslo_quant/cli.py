"""CLI entry point: oslo-quant."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from oslo_quant.config import ALL_FRAMEWORKS, COMPANIES


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oslo-quant",
        description="Oslo Børs quantitative pre-computation system",
    )
    all_tickers = [c.ticker for c in COMPANIES]

    parser.add_argument(
        "--tickers",
        nargs="+",
        metavar="TICKER",
        default=None,
        help=f"Tickers to process (default: all {len(all_tickers)}). E.g. --tickers TEL.OL MOWI.OL",
    )
    parser.add_argument(
        "--frameworks",
        nargs="+",
        metavar="FW",
        choices=ALL_FRAMEWORKS,
        default=None,
        help=f"Frameworks to run (default: all). Choices: {ALL_FRAMEWORKS}",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Ignore raw data cache and re-fetch from APIs",
    )
    parser.add_argument(
        "--period",
        choices=["annual", "ttm", "both"],
        default="annual",
        help="Reporting period (default: annual)",
    )
    parser.add_argument(
        "--output",
        choices=["summary", "full", "none"],
        default="summary",
        help="stdout output level (default: summary)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    from oslo_quant.pipeline import run

    results = run(
        tickers=args.tickers,
        frameworks=args.frameworks,
        force_refresh=args.force_refresh,
        period=args.period,
    )

    if args.output == "summary":
        _print_summary(results)
    elif args.output == "full":
        print(json.dumps(results, indent=2, default=str))

    errors = [t for t, v in results.items() if "error" in v]
    return 1 if errors else 0


def _print_summary(results: dict) -> None:
    print("\n── Oslo Quant Results ──────────────────────────────────────────")
    for ticker, fw_map in results.items():
        if "error" in fw_map:
            print(f"  {ticker:<12}  ERROR: {fw_map['error']}")
            continue
        fw_lines = []
        for fw_name, fw_result in fw_map.items():
            if "error" in fw_result:
                fw_lines.append(f"{fw_name}=ERROR")
            else:
                n = len(fw_result.get("periods", {}))
                fw_lines.append(f"{fw_name}({n}p)")
        print(f"  {ticker:<12}  {', '.join(fw_lines)}")
    print("────────────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    sys.exit(main())
