import argparse
import json
import sys

from .inventory import inventory


def main(argv=None):
    parser = argparse.ArgumentParser(prog="efospec", description="EFOSpec: EFOSC2 spectroscopy with PypeIt")
    commands = parser.add_subparsers(dest="command", required=True)
    telluric = commands.add_parser('telluric', help='Fit one night of standards and independently check atmospheric transfer')
    telluric.add_argument('night')
    telluric.add_argument('--run', required=True)
    telluric.add_argument('--output', required=True)
    telluric.add_argument('--config', required=True)
    telluric.add_argument('--apply-science', action='store_true')
    telluric.add_argument('--review-extrapolation', action='store_true',
        help='Retain time/airmass transfer review products')
    telluric.add_argument('--attach-to-report', action='store_true', help='Render both reductions in the plots and nightly report')
    typing = commands.add_parser('typing-metadata', help='Review revision-bound host and adopted-redshift metadata')
    from .typing_metadata import add_arguments as typing_arguments
    typing_arguments(typing)
    epoch=commands.add_parser('night',help='One dated epoch: observing log, reduction, QC and final report')
    from .nightly import add_arguments
    add_arguments(epoch)
    epoch.add_argument('--stage',choices=['all','log','reduce','report'],default='all')
    gui = commands.add_parser('gui', help='Open the PySide6 desktop extraction application')
    gui.add_argument('path', nargs='?', help='Run, dated workflow folder or review.json; omitted reopens the last night')
    gui.add_argument('--reference-root')
    gui.add_argument('--raw', help='Exact failed raw filename to select for review')
    gui.add_argument('--smoke-test',action='store_true',help='Open the native window, report its runtime, then exit')
    installer=commands.add_parser('install-desktop',help='Install a macOS app or Linux launcher using this EFOSpec environment')
    installer.add_argument('--destination',help='Parent directory; defaults to the user application location')
    joint_check=commands.add_parser('validate-joint',help='Run conditional two-source recovery and uncertainty experiments')
    joint_check.add_argument('--output',required=True)
    joint_check.add_argument('--run',help='Optional saved exposure for injections into its off-source background')
    joint_check.add_argument('--product',help='Product filename within --run')
    joint_check.add_argument('--reference-root')
    joint_check.add_argument('--recipe',help='Explicit two-source joint recipe for real-exposure sensitivity checks')
    browser = commands.add_parser('browser-prototype', help='Legacy local browser extraction prototype')
    browser.add_argument('path')
    browser.add_argument('--reference-root')
    browser.add_argument('--port',type=int,default=0)
    browser.add_argument('--no-browser',action='store_true')
    raw = commands.add_parser('reduce-native', help='Experimental raw-only science/standard pair')
    rescue = commands.add_parser('rescue-daily', help='Explicit provisional flux from audited wavelength-review counts; does not accept failed flexure')
    rescue.add_argument('path',help='Completed same-night parent reduction')
    rescue.add_argument('--night',required=True)
    rescue.add_argument('--output',required=True,help='Fresh provisional revision directory')
    rescue.add_argument('--counts-run',action='append',default=[],help='Additional optical counts run with documented successful background geometry')
    rescue.add_argument('--target',action='append')
    rescue.add_argument('--boxcar-target',action='append',default=[],help='Use finite-aperture boxcar flux as primary; includes extended emission')
    rescue.add_argument('--skip-report',action='store_true')
    rescue.add_argument('--replace-review-counts',action='store_true',help='Explicitly use newly re-extracted counts in place of the parent review counts')
    raw.add_argument('path',help='Night directory with raw calibrations')
    raw.add_argument('--science',required=True)
    raw.add_argument('--standard',required=True)
    raw.add_argument('--science-position',type=float,default=548.)
    raw.add_argument('--standard-position',type=float,default=548.)
    raw.add_argument('--output',required=True)
    raw.add_argument('--skip-report',action='store_true')
    raw.add_argument('--reuse-calibrations',help='Previous raw-only attempt; hashes and associations must match')
    daily = commands.add_parser('reduce-daily', help='One night with raw calibrations and same-night standard responses')
    daily.add_argument('path')
    daily.add_argument('--night', required=True)
    daily.add_argument('--output', required=True)
    daily.add_argument('--target', action='append')
    daily.add_argument('--reviewed-sources')
    daily.add_argument('--calibration-group',action='append',default=[],help='Hash-verified native calibration group to reuse')
    filtered = commands.add_parser('reduce-filtered', help='Separate native Gr13/GG495 standard counts and experimental responses')
    filtered.add_argument('path', help='One observing night of raw data')
    filtered.add_argument('--night', required=True, help='Observing date YYYY-MM-DD')
    filtered.add_argument('--output', required=True, help='Fresh dated revision directory')
    filtered.add_argument('--position', type=float, default=548., help='Expected spatial position in raw pixels')
    filtered.add_argument('--spatial-half-width', type=int, default=100, help='Half-width of the calibrated extraction window in pixels')
    filtered.add_argument('--background-reviews', help='Hash-bound reviewed background recipes for individual standards')
    filtered.add_argument('--calibration-group', action='append', default=[], help='Previously built paired-native calibration directory; repeatable')
    filtered.add_argument('--skip-report', action='store_true')
    red = commands.add_parser('reduce-red', help='Experimental Gr16/OG530 review counts; no accepted flexure or flux calibration')
    red.add_argument('path', help='One observing night of raw data')
    red.add_argument('--night', required=True)
    red.add_argument('--output', required=True, help='Fresh dated revision directory')
    red.add_argument('--position', type=float, default=548.)
    red.add_argument('--spatial-half-width', type=int, default=100)
    red.add_argument('--target', action='append', help='Exact target name; repeatable')
    red.add_argument('--calibration-group', action='append', default=[])
    catalogues = commands.add_parser('acquisition-catalogues', help='Solve acquisition images locally and overlay NED/SDSS/AllWISE catalogues')
    catalogues.add_argument('night', help='One observing date YYYY-MM-DD')
    catalogues.add_argument('--output', required=True, help='Fresh directory inside runs/DATE/QC/')
    catalogues.add_argument('--project-root', default='.')
    catalogues.add_argument('--target', action='append', default=[], help='Exact transient name; repeatable')
    catalogues.add_argument('--catalogue', action='append', choices=['NED','SDSS','AllWISE'], help='Default: all three')
    catalogues.add_argument('--timeout', type=float, default=20, help='Per-service read timeout in seconds')
    catalogues.add_argument('--solver', default='solve-field', help='Local Astrometry.net executable')
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
    qc_source = qc.add_mutually_exclusive_group(required=True)
    qc_source.add_argument('--raw',help='Failed raw exposure')
    qc_source.add_argument('--product',help='Successful product with a recorded visual source identification')
    qc.add_argument('--output', required=True, help='Fresh subfolder inside runs/YYYY-MM-DD/QC')
    qc.add_argument('--reference-root')
    qc.add_argument('--test-recipes', action='store_true')
    background = commands.add_parser('background-extract', help='Experimental polynomial sky+host background and boxcar counts')
    background.add_argument('--native-flux',action='store_true',help='Use bounded native PypeIt and checked same-night response; wavelength failures block export')
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
    rapid.add_argument('--reviewed-sources',help='Exposure-bound recipes and visual target-identification evidence')
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
        if args.command == 'telluric':
            from .telluric_night import execute
            return execute(args)
        if args.command == 'night':
            from .nightly import run_epoch,exit_code
            return exit_code(run_epoch(args.night,stage=args.stage,project_root=args.project_root,plot_python=args.plot_python,
                                       native_calibrations=args.native_calibrations,targets=args.target,
                                       reviewed_sources=args.reviewed_sources,flux_calibration=args.flux_calibration,
                                       calibration_groups=args.calibration_group,iraf_comparison=args.iraf_comparison))
        if args.command == 'background-gui':
            from .background_gui import launch
            return launch(args.packet)
        if args.command == 'background-extract':
            from pathlib import Path
            from .polynomial_background import extract_background
            if args.native_flux:
                from .native_recovery import extract_native as extract_background
            result=extract_background(args.path,args.failed_raw,json.loads(Path(args.recipe).read_text()),
                                      args.output,**({} if args.native_flux else {'reference_root':args.reference_root}))
            print(json.dumps(result,indent=2,allow_nan=False))
            return 0
        if args.command == 'recovery-qc':
            from .recovery_qc import build_recovery_qc, build_reviewed_qc
            if args.product:
                if args.test_recipes:raise ValueError('reviewed-product QC does not run candidate trials')
                result=build_reviewed_qc(args.path,args.product,args.output,args.reference_root)
            else:
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
        if args.command == 'typing-metadata':
            from .typing_metadata import command
            print(json.dumps(command(args), indent=2, allow_nan=False))
            return 0
        if args.command == 'gui':
            from .desktop import launch
            options = {'raw':args.raw} if args.raw else {}
            if args.smoke_test:options['smoke_test']=True
            return launch(args.path,args.reference_root,**options)
        if args.command == 'install-desktop':
            from .desktop_install import install_desktop
            print(json.dumps(install_desktop(args.destination),indent=2))
            return 0
        if args.command == 'validate-joint':
            from pathlib import Path
            from .joint_validation import save_validation
            if args.run and not args.product:raise ValueError('--run requires an explicit --product')
            if (args.product or args.recipe) and not args.run:raise ValueError('--product and --recipe require --run')
            recipe=json.loads(Path(args.recipe).read_text()) if args.recipe else None
            result=save_validation(args.output,run=args.run,product=args.product,reference_root=args.reference_root,recipe=recipe)
            print(json.dumps({'conditional_tests_passed':result['conditional_tests_passed'],
                              'science_validated':result['science_validated'],'output':args.output}))
            return 0 if result['conditional_tests_passed'] else 1
        if args.command == 'acquisition-catalogues':
            from .acquisition_catalogues import check_acquisition_catalogues
            from .field_catalogues import CATALOGUES
            result = check_acquisition_catalogues(args.night, args.output, project_root=args.project_root,
                targets=args.target, catalogues=args.catalogue or CATALOGUES, timeout=args.timeout, solver=args.solver)
            print(json.dumps({'night':args.night,'status':result['status'],'fields':len(result['fields']),
                              'output':args.output,'host_identification':'not_assigned'}))
            return int(result['status'] != 'complete')
        if args.command == 'reduce-red':
            from .filtered_reduction import reduce_red_night
            result = reduce_red_night(args.path, args.output, night=args.night, position=args.position,
                spatial_half_width=args.spatial_half_width, calibration_groups=args.calibration_group,
                targets=args.target)
            print(json.dumps({'output_dir':result['output_dir'], 'counts_extracted':len(result['results']),
                              'errors':[{k:r[k] for k in ('object','error','log')} for r in result['errors']],
                              'science_validated':False}))
            return int(result['status'] != 'complete')
        if args.command == 'rescue-daily':
            from .rescue import rescue_daily, build_rescue_report
            result=rescue_daily(args.path,args.output,night=args.night,counts_runs=args.counts_run,
                targets=args.target,boxcar_targets=args.boxcar_target,replace_review_counts=args.replace_review_counts)
            report=None if args.skip_report else build_rescue_report(args.output)
            print(json.dumps(dict(output=result['output_dir'],provisional_spectra=len(result['results']),
                errors=result['errors'],wavelength_validated=False,report=report)))
            return int(bool(result['errors']) or (report is not None and report['status']!='complete'))
        if args.command == 'reduce-filtered':
            from .filtered_reduction import reduce_filtered_night
            result = reduce_filtered_night(args.path, args.output, night=args.night, position=args.position,
                spatial_half_width=args.spatial_half_width, calibration_groups=args.calibration_group,
                background_reviews=args.background_reviews, render_report=not args.skip_report)
            print(json.dumps({'output_dir': result['output_dir'], 'counts_extracted': len(result['results']),
                'errors': result['errors'], 'report': result.get('report'), 'science_validated': False}))
            return int(result['status'] != 'complete' or result.get('report', {}).get('status') == 'incomplete')
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
        if args.command == 'reduce-daily':
            from .daily_reduction import reduce_daily
            result = reduce_daily(args.path,args.output,night=args.night,targets=args.target,
                                  reviewed_sources=args.reviewed_sources,calibration_groups=args.calibration_group)
            print(json.dumps(dict(output_dir=result['output_dir'], status=result['execution_status'],
                                  spectra=len(result['results']), counts=len(result['counts']),
                                  exposure_states=result['exposure_states'],
                                  errors=result['errors'], skipped=result['skipped']),indent=2))
            return 0 if result['execution_status']=='complete' else 1
        if args.command == 'reduce-rapid':
            from .rapid import reduce_night
            result = reduce_night(args.path, args.output, args.reference_root,
                                  targets=args.target, include_standards=args.include_standards,
                                  plot_python=args.plot_python, skip_report=args.skip_report,
                                  reviewed_sources=args.reviewed_sources)
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
