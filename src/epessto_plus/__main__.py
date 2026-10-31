"""Inventory and calibration planning without executing a reduction."""
import argparse
import json
import sys
from .inventory import inventory


def main(argv=None):
    parser = argparse.ArgumentParser(description="EFOSC2 inventory and calibration planning")
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("inventory", help="Inventory FITS inputs")
    scan.add_argument("paths", nargs="+")
    plan = commands.add_parser("plan", help="Plan calibration associations without reducing")
    plan.add_argument("paths", nargs="+")
    plan.add_argument("--profile", choices=("rapid", "full"), default="full")
    plan.add_argument("--reference-root", default="trunk/src/ntt")
    plan.add_argument("--arc", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        result = inventory(args.paths + getattr(args, "arc", []))
        if args.command == "plan":
            from .planning import build_plan
            result = build_plan(result, args.reference_root, args.profile, args.arc)
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(2, f"{args.command}: {exc}\n")
    json.dump(result, sys.stdout, indent=2, allow_nan=False)
    sys.stdout.write("\n")
    return 1 if result.get("errors") else 0


if __name__ == "__main__":
    sys.exit(main())
