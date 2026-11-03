# Bounded PypeIt backgrounds

New nightly reductions and the desktop editor use bounded, two-sided PypeIt
backgrounds. The confirmed unit is spatial detector pixels: prefer 30 pixels
per side, narrowing to 15 when crowded. GUI widths can be set from 15 to 50.
The default spatial model is quadratic; degrees 1–3 are selectable. Existing
`automatic` recipes retain the old algorithm through explicit legacy replay.
New automatic recipes use `bounded`; anchored recipes use `pypeit_local`.

- Background is spatial: detector pixels or arcseconds. Å describes the
  wavelength direction. Both controls must have separate units in the GUI.
- One finite band on each side, outside the aperture and source wings. The
  nearest clean band moves past saved neighbours when necessary; its width
  never expands to the detector edge. Insufficient room raises a recorded
  `background_support_required` error.
- Degrees 1, 2 and 3 select a slope, quadratic or cubic spatial model. A smooth,
  uneven host background can motivate curvature; nearby peaks alone do not
  establish that it is a galaxy. Compare residuals before accepting an order.
- The actual fit uses PypeIt 1.14.0 `bspline_profile`: spectral B-splines times
  `degree+1` spatial Legendre terms, followed by PypeIt optimal extraction with
  `no_local_sky=True`. This mode is distinct from the existing NumPy polynomial
  boxcar experiment.
- No silent constant-order fallback or positive log-sky prefit. The latter's
  constant spatial model can reject a real gradient. Non-convergence stops the
  trial and records the requested degree and PypeIt exit code.
- At least five accepted pixels on each side after rejection. Unsupported rows
  are masked; losing more than 10% stops extraction. A fitted source trace
  crossing the selected background also stops extraction.
- Saved NPZ files retain the input and accepted masks, side counts, valid rows
  and spatial degree. Product QA records convergence, settings and limitations.
- Fixed-sky PypeIt uncertainties do not propagate fitted background covariance.
  This is not validated SN/host deblending. Saved candidate guards are
  conservative: old records lack neighbour FWHM measurements.

## One date, explicit targets

Inspect the saved geometry and create house-style QC and candidate recipes:

```sh
python scripts/test_local_background.py 2026-10-28 --targets 2026ayt 2026agwm
python scripts/build_epoch_fieldnotes.py 2026-10-28
```

This checks 30, 40 and 50 **spatial pixels** as alternatives without selecting
a default or extracting new spectra. Outputs live under
`runs/2026-10-28/QC/local-background-<revision>/`.

An explicit `--width-pixels N` runs linear
and quadratic PypeIt candidate trials in fresh revisions; `--degrees 1 2 3`
adds a cubic comparison. Source identities remain unverified, including every
SN2026ayt candidate. No C3 choice from SN2026aebl transfers to these exposures.

The completed 2026-10-28 trial invocation was:

```sh
python scripts/test_local_background.py 2026-10-28 --targets 2026ayt 2026agwm --width-pixels 30 --minimum-width-pixels 15 --padding-pixels 50
```

Padding is an explicit archive-bridge operation, recorded in the recipe and
hashed window geometry. It must reproduce every original data and wavelength
pixel exactly. It cannot expand already processed native-calibration data.
The new pixels still need QC review for contaminants outside the saved traces.

## Evidence and limits

On 2026-10-28, the saved 141-pixel windows allow 30-pixel bands for all three
SN2026ayt candidate hypotheses. The 40/50-pixel alternatives fail. For
AT2026agwm, all 30/40/50-pixel alternatives fail when the other saved candidates
are excluded. Expanding this archived-calibration window by 50 pixels per side
allowed two 30-pixel bands and successful linear/quadratic extractions.
SN2026ayt C2 also extracted with both degrees. C1 and C3 failed the fitted-trace
background-overlap gate. C2's numerical success does not verify its identity.
All products remain experimental, in new dated QC revisions; the accepted
epoch spectra and current-revision pointer were not replaced.

Synthetic tests cover curved traces, neighbouring sources, cosmic-ray
rejection, quadratic-background recovery, PypeIt optimal flux recovery,
non-convergence, loss of one-sided support and hash-bound revision replay.

References: [PypeIt 1.14 sky subtraction](https://pypeit.readthedocs.io/en/1.14.0/skysub.html),
and the installed 1.14.0 `pypeit/core/skysub.py` and `core/fitting.py` source.
The adapter calls the underlying solver directly to retain its rejection mask
and convergence status, which `global_skysub` does not return.
