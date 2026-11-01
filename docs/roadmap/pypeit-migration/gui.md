# Desktop extraction roadmap

- **Selected:** PySide6/Qt for macOS and Linux.
- **Implemented:** desktop viewer, source/background controls, recipes and subprocess workers.
- **Verified locally:** macOS Cocoa window, Qt interaction tests, real worker/replay/cancellation.
- **Linux:** XCB/Xvfb interactions, real workers and replay pass [CI](https://github.com/sPaMFouR/EFOSpec/actions/runs/41262157980).
- [Usage](../../desktop.md) · [Evidence](../../native-desktop-validation.md) · [Rules](../../../AGENTS.md).

| Interface | Responsibility |
| --- | --- |
| Qt desktop | Open nights; edit trace/aperture/sky; run/cancel; inspect revisions |
| Shared Python/PypeIt | Validate, calibrate, extract and export |
| Fieldnotes webpage | Read-only nightly table, three diagnostic views and downloads |

## Delivered controls

- Native folder/file pickers; no localhost service or WebView.
- Spectrum, sky-subtracted 2D detector image and binned spatial profiles.
- Click source anchors; edit FWHM/radius; drag/edit background bands.
- One/two sources, immutable revisions, durable cancellation and recipe reload.
- PypeIt optimal/boxcar engine; separate experimental joint fixed-profile engine.
- CLI replay and desktop workers share the same recipe contracts.

## Remaining gates

- Complete a user usability review on each desktop platform.
- Package launchers/installers; add raw-night control only when calibration status is explicit.
- Add crop widening and arbitrary trace-curve editing with coordinate/variance tests.
- Validate extended profiles against trusted SN/galaxy reference extractions.
- Include profile/background uncertainty and spectral covariance before precision deblending claims.
- Reconcile native-calibration changes with the independent two-night debugging branch.

## Scientific contracts

- Coordinates: zero-based raw detector pixels after binning.
- PypeIt manual anchors initialise tracing; the fitted trace may move.
- Joint profiles are fixed Gaussians sharing measured curvature; host identity is not inferred.
- Background order uses held-out sky, never source pixels; retain plausible alternatives.
- Preserve primary names; companions append `_obj_<stable-ID>`.
- Save hashes, source snapshots, recipes and new products; never overwrite inputs.
- Native calibration and GUI usability require separate evidence.

[Parent plan](README.md) · [Engine boundaries](../../pipeline-stages.md)
