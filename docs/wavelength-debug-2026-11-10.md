# EFOSpec / 28 October 2026 / Wavelength debugging

## Finding from the 10 November audit

The current red PypeIt/Paranal correlations are not reliable exposure-flexure
checks for the three Gr13 rescue exposures. This weakens the earlier argument
that those correlations contradict the optical anchors. It does **not** validate
the anchor shifts or establish the cause of the underlying wavelength errors.

Diagnostic revision:
[`manual-wavelength-audit-20261110T121755Z`](../runs/2026-10-28/QC/manual-wavelength-audit-20261110T121755Z/audit.json).
The saved `audit.py` replays existing estimators without changing their thresholds.
It records input/profile/script hashes and unchanged nightly/rescue pointer hashes.
All four raw exposures were processed using their current native calibrations;
no wavelength correction, extracted product, report or pointer was replaced.

### Coordinate-shift sensitivity

Add a known offset to the saved wavelength coordinates, leaving flux fixed.
The estimated correction should respond by the opposite amount. In 6800–7400 A,
adding +10 A changes the correction by:

| Exposure | Expected change (A) | Measured change (A) |
| --- | ---: | ---: |
| SN2026abgb | -10 | -1.42 |
| AT2026agzp (Gr11 control) | -10 | -9.30 |
| AT2026agvs | -10 | +0.20 |
| SN2026aebl | -10 | -0.28 |

The 7400–8000-A Gr13 comparisons also underrespond. The optical Gr13
correlations underrecover +10 A by about 2.4–2.9 A. All tested offsets
(-10, -5, 0, +5, +10 A), including failed measurements, are retained in JSON.
The fixed requested wavelength windows change sample membership at their edges;
this is an end-to-end estimator-sensitivity check, not a pure fixed-support
translation test, an absolute accuracy measurement or a noise-coverage test.
The detailed cause (e.g. continuum removal, profile mismatch, sampling, edge
effects or insufficient line signal) is not yet isolated.

Figure: [PDF](../runs/2026-10-28/QC/manual-wavelength-audit-20261110T121755Z/correlation-sensitivity.pdf),
[JPG](../runs/2026-10-28/QC/manual-wavelength-audit-20261110T121755Z/correlation-sensitivity.jpg).
Generated with root `plot_style.py`, LaTeX, inward ticks and 300-dpi JPG.

### Spatial partitions

The existing line estimator was replayed for the full interior slit, its two
halves, and local bands at detector columns [448,518) and [579,649). Original
masks and the central +/-30-pixel source exclusion were retained. Additional
sources were not manually reviewed; the partitions share the arc solution and
are not independent wavelength standards. Narrow bands have less signal.

- **AT2026agzp:** full-slit 5577/6300 corrections are -5.12/-4.91 A;
  the halves give -5.12/-4.70 and -5.15/-5.11 A. The right half fails the
  6300 signal gate. Full and left-half held-out 6363 residuals are -4.22
  and -4.92 A. Prioritize the 6363 identification/profile and detector pixels.
- **AT2026agvs:** full and half-slit 5577/6300 differences are 3.19, 3.04
  and 2.98 A. A binary threshold flips across these partitions while the
  underlying disagreement persists. The right half then fails the 6363 error
  gate. A single contaminated slit patch does not adequately explain this.
- **SN2026aebl:** the full slit, both halves and local right band pass the
  existing gates. The local left band fails the 6363 formal-error gate.
  This is the best Gr13 control for the reference reduction, still provisional.
- **SN2026abgb:** full and left-half checks pass; the other partitions fail
  signal, centroid-error or held-out gates. Further spatial QA remains necessary.

## What the primary references say

- [Smartt et al., PESSTO, section 3.2.4](https://arxiv.org/html/1411.0299v1#S3.SS2.SSS4):
  arc calibration followed by an exposure sky/telluric offset is established
  practice. The paper describes rotational flexure as a rigid displacement.
  Its quoted 1-A precision is a property of its library-based procedure,
  not a universal centroid-error threshold for these data.
- [ESO EFOSC2 pipeline manual, section 9.8.3 and appendix A.4.1](https://ftp.eso.org/pub/dfs/pipelines/instruments/efosc/efosc-pipeline-manual-1.1.pdf):
  inspect sky offsets as a function of slit position and wavelength. A constant
  is the default; a slope can be appropriate when dispersion changes with
  temperature. This is a hypothesis to test, not evidence that these data need
  a slope. Inspect rectified 2D lines as well as scalar fit residuals.
- [IRAF reidentify](https://iraf.readthedocs.io/en/latest/tasks/noao/twodspec/longslit/reidentify.html)
  and [fitcoords](https://iraf.readthedocs.io/en/latest/tasks/noao/twodspec/longslit/fitcoords.html):
  manually inspect IDs, trace them across the slit and fit the coordinate surface.
- [PypeIt flexure guidance](https://pypeit.readthedocs.io/en/1.18.1/calibrations/flexure.html):
  inspect correlation QA, match the reference resolution, and consider a more
  appropriate sky template. This documentation is newer than installed 1.14.0;
  the installed implementation was inspected directly for the audit.
- [ESO EFOSC2 grism guidance](https://www.eso.org/sci/facilities/lasilla/instruments/efosc/inst/Efosc2Grisms.html):
  attached arcs are recommended when accurate wavelengths are required.

## Next reduction experiment

1. Make a separate IRAF reference reduction for the same 28 October raw data:
   SN2026aebl as the Gr13 control, AT2026agvs as the Gr13 failure, then
   AT2026agzp/Gr11. Use the selected same-night biases, flats and arcs.
   `cl` and `ecl` launchers exist at `/Users/avinash/.iraf/bin/`, pointing to
   IRAF 2.18; no IRAF execution or reference reduction was performed in this audit.
2. Review central arc IDs against the physical He-Ar atlas (`identify`),
   propagate them across the slit (`reidentify`), inspect the 2D surface
   (`fitcoords`) and transform copies. Compare lamp residuals with the native
   map at matching detector coordinates. Existing lamp tests reuse fitted IDs:
   they do not certify science flexure. Check air/vacuum, topocentric convention,
   axis orientation, binning, pixel origin and shift sign explicitly.
3. Inspect original detector stamps around 5577, 6300 and 6363 before spatial
   averaging. Fit native-pixel samples with propagated variance and pixel
   integration, checking cosmic-ray masks, neighbours, continuum and empirical
   line shape. Record manually rejected pixels/lines with a reason. Do not
   constrain a held-out line to the anchor shift and then call it validation.
4. Compare constant-A, constant-pixel and (only if warranted) affine corrections
   using additional usable sky groups across the spectrum. Red OH groups need
   a resolution-matched model with adequate signal; instrument-specific PESSTO
   sky templates are available locally, but their wavelength provenance must
   be checked before treating them as an absolute reference. Where measurable,
   science-frame telluric absorption provides a separate feature family; stellar
   slit centring can differ from slit-filled sky illumination. A different star's
   tellurics do not independently validate a science exposure.
5. Test any candidate estimator on positive/negative injected shifts, fixed-support
   controls, realistic masks/noise and disjoint wavelength groups. For the red
   correlation specifically, isolate window edges, continuum and profile matching
   one at a time. Hold out usable lines/groups and verify residuals after correction.
6. Only then implement the demonstrated fix, propagate the measured calibration
   uncertainty, rerun into a new dated revision and review before promotion.
   If 6363 cannot provide a reliable measurement, an alternative validation policy
   needs independently supported features and calibrated uncertainty; merely
   removing the gate would not resolve the discrepancy.

The preserved legacy pipeline already performs `identify/reidentify -> fitcoords
-> transform -> sky-template correlation` in `trunk/src/ntt/efoscspec2Ddef.py`.
It offers manual review but does not require the current held-out 6363 gate.
Its ability to output a spectrum therefore is not proof that our residual has
been explained. Reproduce its useful manual checks rather than copying its
acceptance behaviour. Do not modify `trunk/` or the separate `pessto` baseline.

Verification: the full-slit diagnostic reproduces the previous four statuses;
all five spatial partitions per exposure and 60 requested correlation trials
are recorded, including unavailable/bad fits. Pointer hashes are unchanged.
No production code was changed and no new automated test pass is claimed.
`git diff --check` reports a pre-existing blank line at EOF in
`tests/test_local_sky.py:364`; that unrelated file was left untouched.
