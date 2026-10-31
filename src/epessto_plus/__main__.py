import argparse
import json
import sys

from .inventory import inventory


def main(argv=None):
    parser = argparse.ArgumentParser(description="EFOSC2 migration tools and experimental rapid reduction")
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("inventory", help="Inventory FITS inputs as JSON on stdout")
    scan.add_argument("paths", nargs="+")
    native = commands.add_parser('native-readiness', help='Check raw calibration availability without IRAF references or fallback')
    native.add_argument('paths', nargs='+')
    rapid = commands.add_parser('reduce-rapid', help='Experimental archived-calibration/PypeIt reduction')
    rapid.add_argument('path', help='Night directory; raw inputs remain read-only')
    rapid.add_argument('--output', required=True, help='Fresh run directory')
    rapid.add_argument('--reference-root', default='trunk/src/ntt')
    rapid.add_argument('--target', action='append', help='OBJECT value to select; repeatable')
    rapid.add_argument('--include-standards', action='store_true')
    rapid.add_argument('--plot-python', help='Python with house-style dependencies (default: EPESSTO_PLOT_PYTHON or current Python)')
    rapid.add_argument('--skip-report', action='store_true', help='Reduce without generating plots/HTML')
    report = commands.add_parser('report', help='Generate an offline Fieldnotes page and diagnostic plots')
    report.add_argument('path', help='Completed rapid run directory')
    report.add_argument('--plot-python', help='Python with SciencePlots, pypalettes, Matplotlib and LaTeX')
    report.add_argument('--existing-plots', action='store_true', help='Rebuild HTML using existing figures only')
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
        if args.command == 'report':
            from .report import build_report
            result = build_report(args.path, plot_python=args.plot_python,
                                  render_plots=not args.existing_plots)
            print(json.dumps(result, indent=2))
            return 0 if result['status'] == 'complete' else 1
        if args.command == 'qa':
            from .qa import make_report
            result = make_report(args.path, args.legacy, args.standards, args.reference_root)
            json.dump(result, sys.stdout, indent=2, allow_nan=False)
            sys.stdout.write('\n')
            return 0
        if args.command == 'reduce-rapid':
            from .rapid import reduce_night
            result = reduce_night(args.path, args.output, args.reference_root,
                                  targets=args.target, include_standards=args.include_standards,
                                  plot_python=args.plot_python, skip_report=args.skip_report)
            print(json.dumps({'output_dir':result['output_dir'], 'reduced':len(result['results']),
                              'errors':result['errors'], 'skipped':result['skipped'],
                              'report':result.get('report')},indent=2))
            return 1 if result['errors'] or result.get('report', {}).get('status') == 'incomplete' else 0
        result = inventory(args.paths + getattr(args, "arc", []))
        if args.command == 'native-readiness':
            from .native_readiness import assess_native_readiness
            result = assess_native_readiness(result)
            print(json.dumps(result, indent=2, allow_nan=False))
            return 0 if result['reduction_ready'] else 1
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
