"""Convert an oscilloscope/meter CSV capture into CircuitPulse voltage-trace JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from logic.trace_import import TraceImportError, import_voltage_csv


def _mapping(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("Channel mappings use CSV_HEADER=REVIEWED_NET.")
    header, net = (part.strip() for part in value.split("=", 1))
    if not header or not net:
        raise argparse.ArgumentTypeError("Channel mappings use non-empty CSV_HEADER=REVIEWED_NET.")
    return header, net


def main() -> None:
    parser = argparse.ArgumentParser(description="Import timestamped voltage CSV evidence.")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--channel", required=True, action="append", type=_mapping,
                        help="Map a voltage CSV column to a reviewed net, e.g. --channel CH1=VCC")
    parser.add_argument("--output", type=Path, help="JSON destination; defaults to stdout")
    args = parser.parse_args()
    mappings = dict(args.channel)
    if len(mappings) != len(args.channel):
        raise SystemExit("Each CSV channel header may be mapped only once.")
    try:
        result = import_voltage_csv(args.csv, mappings)
    except TraceImportError as error:
        raise SystemExit(f"TRACE_NOT_READY: {error}") from error
    encoded = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
