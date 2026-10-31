import argparse
import json
import sys

from .inventory import inventory


def main(argv=None):
    parser = argparse.ArgumentParser(description="EFOSC2 migration tools and experimental rapid reduction")
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("inventory", help="Inventory FITS inputs as JSON on stdout")
    scan.add_argument("paths", nargs="+")
    rapid = commands.add_parser('reduce-rapid', help='Experimental archived-calibration/PypeIt reduction')
    rapid.add_argument('path', help='Night directory; raw inputs remain read-only')
    rapid.add_argument('--output', required=True, help='Fresh run directory')
    rapid.add_argument('--reference-root', default='trunk/src/ntt')
    rapid.add_argument('--target', action='append', help='OBJECT value to select; repeatable')
    rapid.add_argument('--include-standards', action='store_true')
    qa = commands.add_parser('qa', help='Plot rapid products against legacy spectra and standards')
    qa.add_argument('path', help='Completed rapid run directory')
    qa.add_argument('--legacy', required=True, help='Directory with baseline legacy spectra')
    qa.add_argument('--standards', help='Optional completed standard-star run directory')
    qa.add_argument('--reference-root', default='trunk/src/ntt')
    for name, help_text in (("plan", "Plan raw calibration associations without reducing"),
                            ("inspect-pypeit", "Test native PypeIt metadata and raw reading")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("paths", nargs="+")
        command.add_argument("--profile", choices=("rapid", "full"), default="full")
        command.add_argument("--reference-root", default="trunk/src/ntt",
                             help="Legacy ntt directory containing standard/ reference files")
        command.add_argument("--arc", action="append", default=[], help="Explicit raw arc; repeatable")
    args = parser.parse_args(argv)
    try:
        if args.command == 'qa':
            from .qa import make_report
            result = make_report(args.path, args.legacy, args.standards, args.reference_root)
            json.dump(result, sys.stdout, indent=2, allow_nan=False)
            sys.stdout.write('\n')
            return 0
        if args.command == 'reduce-rapid':
            from .rapid import reduce_night
            result = reduce_night(args.path, args.output, args.reference_root,
                                  targets=args.target, include_standards=args.include_standards)
            print(json.dumps({'output_dir':result['output_dir'], 'reduced':len(result['results']),
                              'errors':result['errors'], 'skipped':result['skipped']},indent=2))
            return 1 if result['errors'] else 0
        result = inventory(args.paths + getattr(args, "arc", []))
        if args.command != "inventory":
            from .planning import build_plan
            plan = build_plan(result, args.reference_root, args.profile, args.arc)
            if args.command == "plan":
                result = plan
            else:
                from .pypeit_adapter import inspect_setup
                result = inspect_setup(result, plan, args.profile)
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(2, f"{args.command}: {exc}\n")
    json.dump(result, sys.stdout, indent=2, allow_nan=False)
    sys.stdout.write("\n")
    return 1 if result.get("errors") else 0


if __name__ == "__main__":
    sys.exit(main())
