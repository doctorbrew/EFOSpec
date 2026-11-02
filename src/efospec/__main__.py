import argparse
import json
import sys

from .inventory import inventory


def main(argv=None):
    parser = argparse.ArgumentParser(prog="efospec", description="EFOSpec: EFOSC2 spectroscopy with PypeIt")
    commands = parser.add_subparsers(dest="command", required=True)
    epoch=commands.add_parser('night',help='One dated epoch: observing log, reduction, QC and final report')
    from .nightly import add_arguments
    add_arguments(epoch)
    epoch.add_argument('--stage',choices=['all','log','reduce','report'],default='all')
    gui = commands.add_parser('gui', help='Open the PySide6 desktop extraction application')
    gui.add_argument('path', nargs='?', help='Completed run directory; omitted opens a file picker')
    gui.add_argument('--reference-root')
    browser = commands.add_parser('browser-prototype', help='Legacy local browser extraction prototype')
    browser.add_argument('path')
    browser.add_argument('--reference-root')
    browser.add_argument('--port',type=int,default=0)
    browser.add_argument('--no-browser',action='store_true')
    raw = commands.add_parser('reduce-native', help='Experimental raw-only science/standard pair')
    raw.add_argument('path',help='Night directory with raw calibrations')
    raw.add_argument('--science',required=True)
    raw.add_argument('--standard',required=True)
    raw.add_argument('--science-position',type=float,default=548.)
    raw.add_argument('--standard-position',type=float,default=548.)
    raw.add_argument('--output',required=True)
    raw.add_argument('--skip-report',action='store_true')
    raw.add_argument('--reuse-calibrations',help='Previous raw-only attempt; hashes and associations must match')
    revision = commands.add_parser('reextract', help='Replay a saved manual or automatic recipe')
    revision.add_argument('path')
    identity = revision.add_mutually_exclusive_group(required=True)
    identity.add_argument('--product', help='Original product filename')
    identity.add_argument('--failed-raw', help='Raw basename of a source-selection failure')
    revision.add_argument('--recipe', required=True, help='Saved JSON recipe')
    revision.add_argument('--output', required=True, help='New revision directory')
    revision.add_argument('--reference-root')
    revision.add_argument('--skip-report', action='store_true')
    recovery = commands.add_parser('prepare-recovery', help='Write candidate recipes for a failed exposure; no extraction')
    recovery.add_argument('path')
    recovery.add_argument('--raw',required=True)
    recovery.add_argument('--output',required=True)
    recovery.add_argument('--reference-root')
    qc = commands.add_parser('recovery-qc', help='Create images and unverified candidate trials for a source-selection failure')
    qc.add_argument('path', help='Run containing current failed-exposure diagnostics')
    qc.add_argument('--raw', required=True)
    qc.add_argument('--output', required=True, help='Fresh subfolder inside runs/YYYY-MM-DD/QC')
    qc.add_argument('--reference-root')
    qc.add_argument('--test-recipes', action='store_true')
    background = commands.add_parser('background-extract', help='Experimental polynomial sky+host background and boxcar counts')
    background.add_argument('path')
    background.add_argument('--failed-raw',required=True)
    background.add_argument('--recipe',required=True)
    background.add_argument('--output',required=True)
    background.add_argument('--reference-root')
    editor=commands.add_parser('background-gui',help='Experimental native desktop aperture/background editor')
    editor.add_argument('packet',help='QC exposure review.json')
    download = commands.add_parser('download', help='Download a night of raw EFOSC2 data into data/YYYY-MM-DD')
    download.add_argument('night', help='Observing night YYYY-MM-DD (noon UTC to following noon)')
    download.add_argument('--output-root', default='data')
    download.add_argument('--programme', help='Optional ESO programme/run identifier')
    download.add_argument('--spectra-only', action='store_true', help='Exclude imaging/acquisition frames from the night query')
    download.add_argument('--with-calibrations', action='store_true', help='Also retrieve associated raw calibrations, including other dates')
    download.add_argument('--dry-run', action='store_true', help='Save the selection without downloading FITS')
    download.add_argument('--public-only', action='store_true', help='Ignore ESO credentials and attempt anonymous downloads')
    scan = commands.add_parser("inventory", help="Inventory FITS inputs as JSON on stdout")
    scan.add_argument("paths", nargs="+")
    native = commands.add_parser('native-readiness', help='Check raw calibration availability without IRAF references or fallback')
    native.add_argument('paths', nargs='+')
    calibrate = commands.add_parser('calibrate-native', help='Build experimental raw masters and wavelength/tilt calibrations')
    calibrate.add_argument('paths', nargs='+')
    calibrate.add_argument('--output', required=True, help='New calibration run directory')
    calibrate.add_argument('--grism', action='append', choices=['Gr11','Gr13','Gr16'])
    calibrate.add_argument('--group', action='append', help='Selected calibration group ID; repeatable')
    calibrate.add_argument('--template-map', help='JSON mapping group IDs to successful native group directories')
    validation = commands.add_parser('validate-native', help='Apply raw masters and measure diagnostic sky offsets; no science delivery')
    validation.add_argument('path')
    validation.add_argument('--output',required=True)
    rapid = commands.add_parser('reduce-rapid', help='Experimental archived-calibration/PypeIt reduction')
    rapid.add_argument('path', help='Night directory; raw inputs remain read-only')
    rapid.add_argument('--output', required=True, help='Fresh run directory')
    rapid.add_argument('--reference-root', default='trunk/src/ntt')
    rapid.add_argument('--target', action='append', help='OBJECT value to select; repeatable')
    rapid.add_argument('--include-standards', action='store_true')
    rapid.add_argument('--plot-python', help='Python with house-style dependencies (default: EFOSPEC_PLOT_PYTHON or current Python)')
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
        if args.command == 'night':
            from .nightly import run_epoch,exit_code
            return exit_code(run_epoch(args.night,stage=args.stage,project_root=args.project_root,plot_python=args.plot_python))
        if args.command == 'background-gui':
            from .background_gui import launch
            return launch(args.packet)
        if args.command == 'background-extract':
            from pathlib import Path
            from .polynomial_background import extract_background
            result=extract_background(args.path,args.failed_raw,json.loads(Path(args.recipe).read_text()),
                                      args.output,args.reference_root)
            print(json.dumps(result,indent=2,allow_nan=False))
            return 0
        if args.command == 'recovery-qc':
            from .recovery_qc import build_recovery_qc
            result=build_recovery_qc(args.path,args.raw,args.output,args.reference_root,
                                     test_recipes=args.test_recipes)
            print(json.dumps(result,indent=2,allow_nan=False))
            return int(any(c.get('trial',{}).get('execution')=='failed' for c in result['candidates']))
        if args.command == 'validate-native':
            from .native_validation import validate_native_run
            result=validate_native_run(args.path,args.output)
            print(json.dumps(result,indent=2,allow_nan=False))
            return 0 if result['status']=='complete' else 1
        if args.command == 'calibrate-native':
            from .native_calibration import calibrate_night
            from pathlib import Path
            templates = json.loads(Path(args.template_map).read_text()) if args.template_map else None
            result = calibrate_night(args.paths,args.output,grisms=args.grism,
                                     templates=templates,group_ids=args.group)
            print(json.dumps(result,indent=2,allow_nan=False))
            return 0 if result['status'] == 'complete' else 1
        if args.command == 'gui':
            from .desktop import launch
            return launch(args.path,args.reference_root)
        if args.command == 'reduce-native':
            from .native_reduction import reduce_pair
            result=reduce_pair(args.path,args.science,args.standard,args.output,
                science_position=args.science_position,standard_position=args.standard_position,
                render_report=not args.skip_report,reuse_calibrations=args.reuse_calibrations)
            print(json.dumps({'output_dir':result['output_dir'],'reduced':len(result['results']),
                              'report':result.get('report')}))
            return int(result.get('report',{}).get('status')=='incomplete')
        if args.command == 'browser-prototype':
            from .workbench import serve
            return serve(args.path,args.reference_root,args.port,not args.no_browser)
        if args.command == 'prepare-recovery':
            from .revisions import prepare_recovery
            print(json.dumps(prepare_recovery(args.path,args.raw,args.output,args.reference_root),indent=2))
            return 0
        if args.command == 'reextract':
            from pathlib import Path
            from .revisions import reextract
            result = reextract(args.path,args.product or args.failed_raw,json.loads(Path(args.recipe).read_text()),
                               args.output,args.reference_root,render_report=not args.skip_report,failed=bool(args.failed_raw))
            print(json.dumps({'output_dir':result['output_dir'], 'reduced':len(result['results']),
                              'report':result.get('report')},indent=2))
            return 0
        if args.command == 'download':
            from .download import download_night
            result = download_night(args.night, output_root=args.output_root, programme=args.programme,
                                    spectra_only=args.spectra_only, with_calibrations=args.with_calibrations,
                                    dry_run=args.dry_run, public_only=args.public_only,
                                    progress=lambda message: print(message, file=sys.stderr, flush=True))
            print(json.dumps(result, indent=2))
            return 0 if result['status'] in {'complete', 'planned'} else 1
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
            return 1 if result['errors'] or result['skipped'] or result.get('report', {}).get('status') == 'incomplete' else 0
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
