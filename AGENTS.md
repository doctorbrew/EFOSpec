# EFOSpec project rules

## Interfaces

- **Extraction GUI means a desktop application.** It must provide desktop controls for trace selection, apertures, background regions, and extraction jobs.
- Use PySide6/Qt for macOS and Linux, as selected by the user. Verify platform claims with native Qt interactions.
- Do not substitute a browser editor, localhost service, or WebView wrapper for the requested desktop application.
- **The webpage is the read-only nightly reduction log.** Keep the opening table, per-source spectrum/trace/spatial-profile plots, status, and downloads.
- Do not put extraction controls or job execution into the nightly report. Omit the previously rejected source-selection table column.
- `efospec gui` launches the native PySide6 desktop application; `efospec browser-prototype` retains the earlier browser editor.
- `efospec gui` contains Spectra and Source review tabs. `background-gui` is a compatibility entry point into that same application. Failed-exposure polynomial revisions remain count-level boxcar experiments; see [background workflow](docs/polynomial-background.md).
- Desktop launchers use the dedicated EFOSpec environment. Do not bundle a separate scientific runtime without a new explicit decision.
- Preserve useful prototype code/tests while reusing its Python backend for desktop development. Do not claim the desktop app is delivered until its acceptance gates pass.
- Canonical GUI requirements and tasks: [desktop roadmap](docs/roadmap/pypeit-migration/gui.md).

## Scientific and implementation boundaries

- Keep reduction, calibration, units, masks, and export in the shared Python/PypeIt engine. The desktop frontend edits validated recipes and manages workers.
- New background fits use finite bands on both spatial sides: prefer 30 detector pixels per side, permit narrowing to 15, and expose widths up to 50. Never fall back to the remaining CCD or a one-sided fit. Use the bounded PypeIt path and record the spatial polynomial degree; preserve explicit legacy recipe replay. See [background policy](docs/local-pypeit-background.md).
- Preserve legacy primary filenames, calibration associations, wavelength conventions, and source identifiers.
- Save manual changes in new revisions; never overwrite raw data or accepted products.
- Keep GUI work separate from native calibration validation. Only the experimental raw-only path may claim independence from archived IRAF calibrations.
- Separated two-source extraction does not establish overlapping SN/host deblending or extended-galaxy optimal-extraction accuracy.
- Treat `trunk/` as the preserved legacy baseline; keep the original `../pessto/` checkout and scientific environments separate.

## Epoch workflow

- **The approved Fieldnotes design is the final daily-log format.** Deliver `runs/YYYY-MM-DD/index.html` with the observing log, spectra, issues, source QC, background, calibrations, archive and run record in consecutive sections. Preserve this design for future epochs; make requested refinements incrementally. Use the agent-installed `webpage-spectralog` skill when available.
- Coding-agent skills belong in the user's agent configuration, never in this repository. Keep skill definitions, copies and downloadable skill bundles outside the checkout; the report generator and project documentation remain here.
- Run and report one explicitly named observing date at a time. Prefer `python scripts/reduce_epoch.py YYYY-MM-DD`, or its separate log/reduction/report scripts. The next epoch is a new invocation with a new date; do not introduce an automatic multi-night loop.
- Keep generated epoch files inside the dated revision; group retained calibration sets and older diagnostics under that date's `calibrations/` and `archive/`. Treat legacy compatibility links as read-only paths, not new output destinations.
- Keep the observing date in logs, report titles and parent output paths. Preserve earlier processing revisions. Canonical workflow: [dated scripts](docs/epoch-workflow.md).

## Documentation and verification

- **All new or regenerated scientific plots must use the `plot-style` skill**, including QC, detector images, profiles and diagnostic spectra. Use the existing root `plot_style.py`: SciencePlots, mandatory LaTeX, Hiroshige colours, inward ticks after setting limits, and both PDF + 300-dpi JPG. PNGs may accompany these as report previews. Do not silently use Matplotlib defaults.

- Keep Markdown compact; prefer short bullets and explicit delivered/planned status.
- Use observing-night paths such as `runs/2024-11-14` in instructions. Identify historical test-directory names as internal evidence only.
- Do not describe browser integration tests as desktop-app tests.
- Verify desktop interactions, cancellation, recipe replay, and unchanged scientific outputs on every platform claimed as supported.
- Use focused checks for the changed scope; documentation changes need link/consistency checks, not new implementation-mirroring tests.
