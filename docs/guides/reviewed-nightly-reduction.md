# Reviewed geometry in a full nightly reduction

The dated runner still inventories and attempts every science exposure and
applicable standard when no target filter is supplied. Calibration groups are
rebuilt unless explicitly passed with `--calibration-group`.

A hash-bound `--reviewed-sources` entry may now carry:

- `validation_policy`: `three-line` (default), `two-anchor`, or `full-spectrum`.
  The choice is explicit per reviewed exposure; no failed check silently selects
  another policy. Standards retain their ordinary independent checks.
- `dynamic_background: true`: rerun the six nearby-band/degree comparisons on
  freshly processed native pixels before extraction. Source identity, raw
  aperture and neighbour exclusions come from the reviewed recipe. The saved
  trace is mapped in raw detector coordinates without extrapolation; it is not
  transferred by cosmetic C labels. The selected model and trials are retained
  inside the new exposure directory under `dynamic-background/`.

The selected finite geometry is refitted during native extraction. Detector
masks remain separate from geometric bands. Wavelength failures retain only
explicit arc-grid review counts when background extraction succeeds. Existing
reviewed fixed-band recipes retain their original behavior.

For 2026-10-28, explicit policies retain the reviewed historical C2 aperture for
SN2026ayt, the two-anchor policy for AT2026agzp, and the full-spectrum policy plus
dynamic local bands for AT2026agvs and SN2026abgb. Other exposures use normal
native automatic source/background selection and wavelength checks. This is
supervised reuse of recorded reviews, not unattended source identification.

## Full-night replay on 15 November 2026

Revision `20261115T224937Z-c9a1ea` rebuilt nine native calibration groups from
193 inventoried frames and attempted all eight science and twelve standard
exposures. All twenty produced counts; seven science and ten standards reached
experimental flux export. Twelve response fits and fourteen directed held-out
response transfers completed. No setup was skipped.

The previous full-night run delivered four science flux spectra; its subsequent
manual recoveries brought that to seven. The fresh run reproduces that seven
within the nightly workflow. SN2026abgb now extracts with bounded local bands,
but retains arc-only review counts: regional full-sky wavelength estimates
remain inconsistent. Two Gr16 standards also retain counts pending independent
red-wavelength validation. No wavelength gate was relaxed and absolute flux
accuracy remains unvalidated.

The reduction snapshot preserves the exact working-tree source, including
pre-existing edits. The run's `QC/preflight/` records inputs, recipes, baseline
products and the 32 passing focused tests. This real-night replay establishes
integration for these reviewed exposures, not guaranteed extraction of arbitrary
host-contaminated spectra.
