# EFOSpec desktop recovery continuation

## Scope and state

- User requested pushing the completed GUI work and leaving unresolved issues for a new thread. Do not continue fixing issues until that thread is resumed by the user.
- Current branch: `master`; remote: `origin` (`doctorbrew/EFOSpec`). This handoff accompanies the GUI commit. Existing unrelated reduction/report changes and `pyraf/` remain uncommitted; preserve them.
- Desktop remains native PySide6; the nightly webpage remains read-only. Scientific checks belong to the shared engine. Never overwrite raw data or accepted products or silently relax quality gates.
- Delivered: exact failed-exposure URL selection, queued startup handoffs, live input validation, visible extraction requirements/errors, clickable trace selection and background dragging, clear-band action, explicit saved-trace boxcar versus PypeIt-refit counts, report-style fonts/limits and PDF plus 300-dpi JPG export.
- Key files: `src/efospec/{desktop.py,desktop_canvas.py,background_gui.py,background_qc.py}`, `docs/desktop.md`, `tests/{test_desktop.py,test_review_handoff.py,test_background_gui.py,test_background_plot_style.py}`.

## Scientific evidence and unresolved issues

- Night: `2026-11-25` (ending November 26), revision `runs/2026-11-25/efospec/nightly/20261126T181318Z-c7764e`.
- Download complete: 348 files. Three TDE2026aetp calibrated results; SN2026acxa retained Gr16 review counts; L745a Gr18/Gr20 unsupported; AT2026afvu failed native checks. Overall reduction partial, report complete.
- AT2026afvu raw: `EFOSC.2026-11-26T05:51:24.253.fits`.
- User's original GUI job: `reduction/background-20261126T201105-caff26.json`, with matching logs. It failed: `Parent wavelength check failed; flux recovery withheld`. Original recipe used degree 0; native PypeIt supports degree 1–3.
- User explicitly approved a degree-1 review-counts test using the same source and bands. Geometry: x=549.999, spectral row=518, radius=7, bands=[520,540] and [570,590], clipping=4.
- Test directory: `QC/AT2026afvu-gui-recovery-20261126T191642Z/` inside the revision. `reduction/run.json` records the failed PypeIt trial: extracted trace departs from a degree <=4 polynomial by more than 0.5 pixel. This remains unresolved; do not suppress its gate.
- Separate `saved-trace-boxcar/boxcar-background.fits` succeeded with a degree-1 polynomial and valid background fits in all rows. FLUXCAL=NONE, WAVEVAL=False, all wavelength VALID flags false. This is experimental count-level boxcar evidence, not a scientifically accepted or flux-calibrated spectrum. It is not selected into the nightly report.
- `gui-plots-final/` contains checked PDF/JPG profiles and a native desktop screenshot. GUI display uses median-row profiles; the report uses wavelength-binned sums. Limits/fonts are shared, not those distinct statistics.
- Display spike rejection only excludes isolated spikes/edge columns from axis-limit estimates; all samples stay plotted. It does not repair a failed spectral trace or change scientific masks.

## Verification completed

- Dedicated Python: `/Users/avinash/Softwares/miniconda3/envs/efospec/bin/python`.
- Native macOS Cocoa launch with actual AT2026afvu review URL selected its exact raw filename. Qt mouse-event tests covered trace clicks and band dragging, worker cancellation, recipe serialization/replay, and source-preservation checks.
- `MPLBACKEND=Agg python -m pytest tests/test_background_gui.py tests/test_background_plot_style.py tests/test_desktop.py tests/test_review_handoff.py tests/test_polynomial_background.py -q`: 38 passed. After final overlay cleanup, the two background GUI/style suites passed again: 11 passed.
- LaTeX serif rendering was checked after delayed Qt draws; ticks 23.4 pt, JPG 300 dpi, matching PDFs. Native screenshot and JPG inspected. Relevant saved review-product and successful-exposure raw hashes unchanged.
- New changes were not tested on Linux. No calibrated AT2026afvu recovery or independent absolute-flux validation was established.

## Next actions when the user resumes

1. Inspect the retained native trace diagnostics and reproduce why the manual degree-1 PypeIt trial violates the trace gate. Distinguish true curvature, noise/outliers, and a selection/coordinate issue before changing any method.
2. Diagnose AT2026afvu wavelength consistency independently. Keep review counts and accepted flux separate; do not treat improved background fits as wavelength validation.
3. Review GUI usability with the user after restarting the app: plot/layout density, explicit output modes, actionable failure text, and preservation of choices. Current process does not hot-reload changes.
4. Assess counts-only handoffs separately: `native_recovery.load_failed` currently requires an error record even when a review-counts record exists. Investigate before claiming every pending-calibration exposure supports recovery.
5. Audit existing unrelated dirty changes separately; do not fold them into this work without establishing their ownership and validation.

## Suggested skills

- `diagnosing-bugs` for trace/wavelength failures; `plot-style` for all regenerated diagnostics; `review` when explicitly reviewing the implementation.
- Follow repository `AGENTS.md`, `docs/epoch-workflow.md`, `docs/desktop.md`, and `docs/roadmap/pypeit-migration/gui.md`.
