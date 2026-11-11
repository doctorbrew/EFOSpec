# EFOSpec development log

## 2026-11-11 — Repository cleanup and acquisition display

- Removed the white stroke around the acquisition target's open circle and label;
  coordinates, source pixels and astrometric acceptance rules remain unchanged.
- Grouped legacy PyRAF helpers and original installation notes under
  `trunk/legacy-tools/`; updated the local legacy installation commands.
- Removed stale build distributions and root caches. Archived previous local CI
  reports, badge metrics and coverage under `outputs/housekeeping-20261111/`.
  Its `cleanup.json` records moved-file hashes and removed regenerable artifacts.
- Clarified recursive science-data ignores, added a project index and contributor
  guide, and documented the source / legacy / local-output directory boundaries.
- Kept historical reduction paths and compatibility links: saved scientific
  recipes still depend on them. No reduction engine or raw data was moved.
- Verification: 35 focused acquisition/report tests passed; CLI help and new
  documentation links resolve; nested data/output ignore rules were checked.
  Refreshed the 28 and 29 October acquisition displays in new QC revisions and
  verified the selected reduction manifests, raw acquisitions and figure hashes.

## 2026-11-11 — Acquisition candidate framing and contrast

- Replaced the detector-centre detail view with bounds containing the registered
  target and all in-frame galaxy candidates; explicit empty-catalogue fallbacks.
- Added local light/dark annotation selection from the displayed image’s actual
  normalization and colormap. Label contrast is evaluated after placement.
  Markers remain open and labels remain free of halos.
- Regeneration uses saved catalogues and accepted WCS only; no catalogue queries,
  astrometric solutions or reductions are rerun.
- Verified 21 acquisition/contrast tests and 37 recovery/report tests (overlapping
  catalogue coverage). Refreshed 10 catalogue fields on 28 October and 11 on
  29 October, plus the selected source-review acquisition packet. Confirmed
  unchanged raw acquisition and selected reduction-manifest hashes, current
  figure hashes and portable-report hashes; both reports rebuilt without warnings.
  Verification record: `outputs/housekeeping-20261111/adaptive-verification.json`.

## 2026-11-11 — Boxed acquisition labels

- Replaced adaptive annotation colours with the requested `xkcd:dodger blue`
  for the SN and `xkcd:red` for galaxy candidates, including matching markers.
- Labels use borderless white boxes at `alpha=0.8`, with opaque text. Placement
  includes the box footprint when checking neighbours and image boundaries.
- Retained candidate framing, open markers, saved astrometry and original pixels.
- Verification: 19 focused acquisition tests passed. Display revisions are
  preserved under `QC/target-positions-20261111/displays-v5-boxed/`.
  Refreshed both nightly reports (21 catalogue fields and one source-review
  packet); verified unchanged raw/reduction hashes and current figure/report
  hashes. Each display revision includes `verification.json`.

## 2026-11-11 — Host association and typing metadata

- Added the native **Host & redshift** tab and `typing-metadata` CLI with explicit
  host/adopted-z acceptance, reviewer/time, candidate and provenance retention.
- Added `efospec-typing-metadata/1` exports beside the selected `run.json`, immutable
  metadata snapshots, reduction/spectrum SHA256 checks and stale-edit protection.
- Nightly spectrum cards read the same export. Metadata saves and report refresh
  do not invoke reduction or classification. [Workflow](typing-metadata.md).
- Validated 2026-10-28: four unreviewed science records; no adopted z. The saved
  November 9 host-evidence parent is older than the selected November 10 reduction
  and was rejected. All 504 protected manifests/products/selection files retained
  their hashes; previous opening HTML was archived before refresh.
- Local Spectypus reader accepted the export and all three synthetic accepted-z
  kinds, ignored unaccepted candidate z and rejected stale metadata. Native macOS
  Cocoa launch reported three tabs and ready status. Evidence is in the ignored
  `outputs/typing-metadata-validation-2026-10-28/` directory.


## 2026-11-11 — Acquisition host tags and verification links

- Removed host/reviewer initialization blocks from spectrum panels. Compact tags
  now follow acquisition plots; full evidence and verification links are at the
  bottom of the nightly log.
- Fresh reduction-bound NED queries plus public TNS evidence yielded three
  proposed hosts and one positional counterpart (AT2024afzf, likely Galactic).
  SN2026aebl retains an explicit competing-host/redshift caveat. No z was adopted.
- Added NED, TNS and PESSTO Marshall portal buttons. Kept published narrow-line
  and template redshifts distinct from catalogue redshifts. See [details](typing-metadata.md#proposed-cross-matches-in-the-nightly-log).
- Focused checks: 57 tests passed; 504 protected manifests/products unchanged.

## 2026-11-11 — Final implementation cleanup before publication

- Retained the current acquisition labels, host-verification section and shared
  nightly report renderer. Removed 30 superseded local HTML snapshots and copied
  display-refresh scripts for 2026-10-28 (913 MB); the final compact, portable and
  viewer HTML remain available. Removal hashes are recorded locally in
  `outputs/prepush-20261111/cleanup.json`.
- Preserved metadata revisions, completed reductions, original spectra and
  provenance-linked catalogue/display records. Historical report filenames in
  development verification records identify removed snapshots, not live inputs.
- Kept the production spectrum renderer and supported compatibility entry points;
  they are active dependencies, despite their older filenames. Reference manuals
  remain local and are not included in the publication.
- Validation: dependency consistency and wheel build passed; all 504 protected
  reduction/product files and 117 report assets verified. Native Cocoa startup
  opened the selected night with three tabs. Corrected four stale launcher/crop
  assertions; the corresponding ten tests then passed.
- Full suite: 470 passed, nine failed before those assertion corrections;
  measured coverage 82.34%, below the required 85%. Five existing failures remain:
  four synthetic reduction/replay paths hit the final-trace background-support
  check, and one sky-selection replay differs by less than 0.001 spatial pixel.
  Isolated previous-commit replays reproduced the daily-reduction and sky-selection
  failures. No science gate or coverage threshold was weakened for publication.
  Logs and the baseline comparison are in `outputs/prepush-20261111/`.
- Next individual investigation selected by the observer: SN2026abgb on
  2026-10-28. Keep diagnosis and trial products separate from the selected run.

## 2026-11-11 — Isolated SN2026abgb diagnosis

- Reproduced the original failure from its saved source snapshot with unchanged
  calibration masters. No final background solver call occurred: band placement
  failed around a truncated edge candidate.
- Tracked the real broad neighbour from raw finding through the restricted
  bootstrap search. Current code loses that neighbour's guard and completes a
  trial whose sky bands enter the guard in every row. Kept trial counts unadopted.
- Identified a scoring ring inside the measured source aperture. Recorded the
  evidence, diagnostic figure and bounded follow-up changes in the
  [case report](diagnostics/SN2026abgb-2026-10-28.md). No shared reduction algorithm
  or acceptance threshold changed during this investigation.
