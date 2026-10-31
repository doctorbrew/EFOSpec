# Desktop extraction GUI roadmap

**Requirement clarified: desktop extraction app; webpage for the nightly reduction log.**

- **Desktop app: not implemented.** The current browser editor is an experimental prototype.
- **Reusable backend: implemented.** Shared PypeIt extraction, validated recipes, immutable revisions, and CLI replay.
- **Nightly webpage: implemented.** Read-only Fieldnotes report with an opening table and per-source diagnostic plots.
- Project rules: [AGENTS.md](../../../AGENTS.md). Prototype instructions: [browser editor](../../gui.md).

## Interface ownership

| Interface | Purpose | Required behaviour |
| --- | --- | --- |
| Desktop application | Interactive extraction | Choose traces, apertures, background, and sources; run/cancel extraction; inspect and save revisions |
| Python/PypeIt engine | Scientific processing | Validate inputs/recipes; trace, fit sky, extract, calibrate, and export through shared functions |
| Fieldnotes webpage | Log of a reduced night | Opening exposure table; spectrum, trace, and spatial profile side by side for each source; status and downloads |

- The nightly page must not launch extraction jobs or edit recipes.
- A browser app or WebView wrapper does not satisfy the requested desktop interface.
- Preserve the report theme; desktop interaction design can follow platform conventions.

## Platform decision — open

- Evaluate **Swift/SwiftUI for macOS**, or a suitable desktop toolkit for **macOS/Linux**.
- Settle the supported platforms and toolkit before implementing the desktop frontend.
- Do not promise Linux support for a macOS-only implementation.
- Reuse the `efospec` Python environment; do not rewrite scientific algorithms in Swift or UI code.
- Prefer a subprocess boundary with structured requests, progress, errors, cancellation, and output paths.
- The desktop app should use file/folder pickers; observers should not need a localhost URL or internal test-directory name.

## Delivery tasks

| Task | Scope | Acceptance evidence |
| --- | --- | --- |
| D1 — platform and worker contract | Record toolkit/platform choice; define versioned recipe/job messages and runtime selection | Desktop process starts the pinned Python engine; missing environment produces an actionable error |
| D2 — desktop exposure viewer | Open a night/run; select exposures; inspect spectrum, native detector image, and binned spatial profiles | Actual desktop window and file picker work on each claimed platform; pixel mapping matches saved geometry |
| D3 — extraction editor | Manual anchors, FWHM, aperture, include/exclude sky, optional second source, optimal/boxcar views | Mouse and keyboard edits survive recipe save/reload; invalid selections fail before extraction |
| D4 — workers and revisions | Run/cancel jobs, show progress/errors, inspect products, save new revisions | Desktop and CLI recipes produce matching arrays; cancellation leaves originals unchanged |
| D5 — nightly log and delivery | Refresh the read-only Fieldnotes report from saved results; document app launch/install | Opening table and three plots per source remain; the report has no extraction controls; desktop smoke tests pass |

- Dependencies: D1 → D2 → D3 → D4 → D5.
- First desktop milestone: open an existing reduction and complete a manual re-extraction.
- Raw-night reduction controls must expose the actual supported calibration mode; they cannot imply native calibration is finished.
- Desktop delivery requires desktop UI tests. Existing Chromium tests validate only the browser prototype.

## Backend evidence already available

- Automatic SN2023xxj spectra and validity masks remain unchanged after the shared-engine refactor.
- Browser and headless recipe replay produce identical arrays for the tested inputs.
- Three synthetic noise/brightness cases recover separated-source median flux within 2%.
- Native-pixel coordinates, background selections, input hashes, cancellation, and preserved originals are tested.
- Real SN2023xxj, 2024-11-14: manual extraction and its Fieldnotes report completed through the prototype.
- These results support backend reuse; they do not establish desktop usability or platform support.

## Scientific contracts and remaining limits

- Coordinates: zero-based raw detector pixels after binning; explicit pixel FWHM and boxcar half-width.
- Anchors initialise PypeIt tracing; they do not constrain arbitrary trace curves.
- Explicit sky regions select the global fit, held during extraction; automatic mode retains local refitting.
- Preserve the primary basename; companion products append `_obj_<stable-ID>` before `_f.fits`.
- Bind recipes to input/calibration hashes; save source versions and new revisions.
- Current backend: saved detector window, at most two sources separated by ≥5 FWHM.
- Crop widening, extended profiles, overlapping-source models, and cross-source covariance need separate validation.
- Native raw calibration remains a separate unfinished requirement.

[Parent plan](README.md) · [Engine boundaries](../../pipeline-stages.md)
