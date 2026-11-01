# EFOSpec project rules

## Interfaces

- **Extraction GUI means a desktop application.** It must provide desktop controls for trace selection, apertures, background regions, and extraction jobs.
- Use PySide6/Qt for macOS and Linux, as selected by the user. Verify platform claims with native Qt interactions.
- Do not substitute a browser editor, localhost service, or WebView wrapper for the requested desktop application.
- **The Fieldnotes webpage is the read-only nightly reduction log.** Keep the opening table, per-source spectrum/trace/spatial-profile plots, status, and downloads.
- Do not put extraction controls or job execution into the nightly report. Omit the previously rejected source-selection table column.
- `efospec gui` launches the native Qt app. `efospec browser-prototype` retains the earlier browser editor.
- Preserve useful prototype code/tests while reusing its Python backend for desktop development. Do not claim the desktop app is delivered until its acceptance gates pass.
- Canonical GUI requirements and tasks: [desktop roadmap](docs/roadmap/pypeit-migration/gui.md).

## Scientific and implementation boundaries

- Keep reduction, calibration, units, masks, and export in the shared Python/PypeIt engine. The desktop frontend edits validated recipes and manages workers.
- Preserve legacy primary filenames, calibration associations, wavelength conventions, and source identifiers.
- Save manual changes in new revisions; never overwrite raw data or accepted products.
- Keep GUI work separate from native calibration validation. Only the experimental raw-only path may claim independence from archived IRAF calibrations.
- Separated two-source extraction does not establish overlapping SN/host deblending or extended-galaxy optimal-extraction accuracy.
- Treat `trunk/` as the preserved legacy baseline; keep the original `../pessto/` checkout and scientific environments separate.

## Documentation and verification

- Keep Markdown compact; prefer short bullets and explicit delivered/planned status.
- Use observing-night paths such as `runs/2024-11-14` in instructions. Identify historical test-directory names as internal evidence only.
- Do not describe browser integration tests as desktop-app tests.
- Verify desktop interactions, cancellation, recipe replay, and unchanged scientific outputs on every platform claimed as supported.
- Use focused checks for the changed scope; documentation changes need link/consistency checks, not new implementation-mirroring tests.
