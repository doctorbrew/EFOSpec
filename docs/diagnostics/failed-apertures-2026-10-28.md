# EFOSpec: failed-aperture review, 2026-10-28

## Current display and automatic detection policy

The selected review is now `QC/aperture-labels-20261112/`, retaining the validation
from `QC/SN2026ayt-candidate-validation-20261112/`.
SN2026ayt retains only the former C2, now displayed as **C1** because it is the
only supported aperture. Its historical C1 and C3 lack a supported spatial peak.
Validated profiles number visible apertures consecutively from left to right;
the original candidate IDs and operator selection remain in provenance.
SN2026abgb retains the selected C1 and the broad neighbour relabelled C2.
The latest background-limit and sampling-label changes are preserved.

The former SN2026ayt C1 exposed a second bug after the detector checks were added: the
historical review renderer still drew all saved proposals except those on a
manual hide list. The previous cleanup hid C3 but kept C1 marked "unconfirmed",
despite its failed validation. It was not a valid aperture. Reviewed plots now
consume the measured decision for every candidate; non-selected traces with
failed or missing validation are omitted automatically. Explicit operator
apertures remain explicit. Saved decisions are associated by trace and name,
not by list position; label mappings and all rejected evidence remain recorded.

C1 fails every spectral bin at tested FWHM 4, 8 and 12, in both native data and
saved sky residuals. Its median saved-window coordinate is 60.46; the nearest
left background boundary has median coordinate 66, and C1 is outside that
boundary in all 942 rows. This supports rejection, but does not by itself prove
the exact historical PypeIt detection trigger. The retained reducer snapshot
exported all proposals without the independent peak-validation stage.

The earlier operator-requested cleanup was selected from
`QC/failed-apertures-20261112-v3/`: remove SN2026ayt's old C3 and SN2026abgb's
old C2 marker; label the latter's broad neighbour **C2** instead of N1. Put the
selected C1/C2 label beside its red aperture and omit numeric centre annotations.
The revision records the old-to-new label mapping; old diagnostics remain intact.

Automatic candidates now require both Gaussian contrast and a significant
two-sided turnover in at least three of six spectral bins. The core must exceed
each shoulder by at least three propagated, residual-inflated noise errors;
comparisons use the same detector rows and do not subtract a fitted spatial
slope that could manufacture a peak on a curved wing. A monotonic concave slope
that passed the old contrast-only check now fails. Broad resolved peaks pass.
Weak, emission-line-only and incompletely supported sources still need review;
this criterion is not a guarantee against every possible false detection.

On the saved detector data, SN2026abgb's old C2 and SN2026ayt's C3 pass zero
bins at FWHM 4, 8 and 12. Both selected transient traces pass all six bins at all
three widths; the broad neighbour passes all six at its measured FWHM 18.49.
Failed and successful extraction packets now publish only validated or explicitly
manual candidates. Rejected proposals and their evidence remain in separate
audit arrays, and the original sky masks are preserved. Earlier packets are not
silently rewritten. These changes do not resolve the background-support failures.

## Original review

Reviewed 2026-11-12 against the selected `20261110T170405Z-b97078` reduction.
The failed-profile adapter explicitly disabled aperture shading and selected
centroid markers. It now accepts an operator's hash-bound display selection,
and reports each centroid in its own wavelength interval. This does not accept
an extraction, change the reduction recipe, or refit the background.

- **SN2026ayt: C2.** Retain the existing reviewed 7-pixel aperture radius around
  the saved trace. Blue bands show the actual saved trial sky inputs; final
  trace/background support failed in 21 rows. C2 has positive local contrast in
  all six spectral bins. C1 passes none; C3 passes zero bins at FWHM 4 and only
  two at FWHM 8 or 12. C3 therefore remains unconfirmed, rather than being
  declared nonexistent: a weak or red-only source needs separate review.
- **SN2026abgb: C1.** Shade a proposed 16.20-pixel half-width, 1.5 times its
  initial PypeIt FWHM, explicitly distinct from an accepted extraction aperture.
  C1 passes all six contrast bins at all three tested widths. C2 near 142 fails
  the persistence requirement at every tested width. Restore the initial broad
  neighbour as **N1**, preserving the saved C1/C2 identifiers. N1 near 160 is
  supported in all six bins at its measured FWHM 18.49; host identity is unknown.
  The saved final sky mask is empty, so no blue bands are invented.

PypeIt's `FindObjects` supplies the detections and traces. EFOSpec controls the
search masks, subsequent validation, aperture choice and background guards. In
the older SN2026abgb processing, restricting detection to the preliminary
sky-interpolation interval lost the broader neighbour and produced an edge/wing
candidate. The shared engine now retains independently supported initial
neighbours as contaminants. See [the underlying diagnosis](SN2026abgb-2026-10-28.md).
The selected historical reduction still fails the two-sided-background checks;
these display corrections do not turn that failure into a usable spectrum.

Evidence and PDF/JPG/PNG figures are retained under
`runs/2026-10-28/QC/failed-apertures-20261112-v1/`. Its `build.py` reproduces the
contrast checks using native data, inverse variance and bad-pixel masks; the
spec2d science array matches the diagnostic array exactly after float32 storage
rounding. `selection.json` records operator choices and radius provenance;
`contrast-evidence.json` retains all tested widths and signed bin results.
`preservation.json` verifies 317 original inputs/products unchanged. The report
selects this revision explicitly through `failure-profile-selection.json` and
verifies its manifest, evidence and figure hashes on every rebuild.
