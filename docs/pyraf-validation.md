# EFOSC PyRAF validation — 14 November 2026

Branch: `pyraf-pipeline`. The automated interactive editing path works in the
native Python 3.11 environment. The trial science spectra are **not approved
for release**: source identification, the Gr11 wavelength solution and invalid
Gr11 extraction uncertainties still need resolution.

## Interactive editing

The test uses actual Tk-generated key and cursor events, the installed PyRAF
graphics kernel and IRAF `apedit`/`aptrace`/`apall`. It does not replace IRAF
cursor responses with fabricated strings. It operates on a copy of the saved
vma2 Gr13 aperture and image from `full1d-03`.

The final test, `runs/pyraf-debug/editor-05`, verifies all 15 cursor responses,
saved aperture limits of approximately −6/+7 spatial pixels, sky windows
−35:−25 and 25:35 relative to the aperture centre, changed trace coefficients,
and a finite four-band extraction with shape `(4, 1, 1015)`. Source image and
database hashes are unchanged. `editor-events.json` contains the returned
cursor coordinates and edited aperture database. A previous completed run,
`editor-04`, demonstrated the same edit/extract sequence.

The automated test temporarily filters physical keyboard input in its own
process because incidental keystrokes disrupted an earlier trial. It restores
the original handlers afterward. It raises a graphics window and is **not** a
physical-mouse, focus-switching or DS9 acceptance test.

| Editor | Keys exercised | Meaning |
|---|---|---|
| Aperture | `l`, `u`, `b`, `q` | Lower/upper limits, background editor, finish |
| Background | `z`, paired `s`, `f`, `q` | Remove old intervals, mark each interval's endpoints, refit, return |
| Trace fit | `d`, `f`, `q` | Delete a trial point, refit, save/return |

Background coordinates are **relative to the aperture centre**. A first test
mistakenly supplied absolute spatial pixels and correctly exposed an unusable
background region; that failed evidence is retained in `editor-01`. IRAF's
own graphics retain their native appearance; exported analysis plots use the
requested plot style.

## Scientific checks and fixes

The final reduction starts from 52 raw frames in `2026-10-28`, covering
Gr11/Free, Gr13/Free, Gr13/GG495 and Gr16/OG530 with slit1.0. There are two
science exposures, seven standard exposures and the matching bias/flat/arc
inputs. Full 2D, science 1D and standards-only 1D runs all return zero and
preserve their input hashes. Gr13's paired Free/GG495 second-order code path
executes; its scientific accuracy is not certified by execution alone.

Four defects were reproduced and corrected:

1. Batch reduction with multiple standards prompted and failed on EOF. It now
   uses the existing first-listed default, explicitly logs the choice and
   preserves interactive selection. Both booleans and the CLI's `'no'` string
   are tested. This is not a new algorithm for choosing the best standard.
2. Sensitivity preparation used the last standard's atmospheric model for
   every selected standard. Each standard now uses its own model. The final
   seven cleaned-standard spectra agree numerically with that association.
3. IRAF processes cached wavelength headers across Astropy updates. In the
   minimal reproduction, changing CRVAL1 from 5000 to 4993 left a later IRAF
   result at 5000 until `flprcache`. `updateheader` now flushes an already
   running IRAF cache after WCS changes, without starting PyRAF for FITS-only
   operations. The real-IRAF regression fails before and passes after the fix.
4. Telluric correction left sigma unchanged. IRAF `sarith` explicitly copies
   bands labelled `sigma` without arithmetic, so simply removing the old
   sigma-copy operation was insufficient. The correction now processes sigma
   as a separate primary spectrum using the same transmission and IRAF
   interpolation, then restores it to band 4. Raw/sky diagnostic bands remain
   unchanged. Constant and varying transmission tests with real `BANDID`
   headers pass. This propagates extraction noise conditional on the model;
   atmospheric-model uncertainty is not included.

The final measured sky-line offsets are:

| Trial spectrum | 5577.338 Å | 6300.304 Å | 6363.776 Å |
|---|---:|---:|---:|
| AT2024afzf, Gr13 | −0.58 Å | +0.27 Å | −0.19 Å |
| AT2026agwm, Gr11 | −0.85 Å | +8.34 Å | +6.16 Å |

These are air-wavelength Gaussian-plus-linear-background fits within ±35 Å,
using extracted sky band 3. All six pass the diagnostic peak/residual check
and are away from fit bounds. Formal fit errors, widths and fit flags are
retained in JSON; they exclude wavelength systematics. Sky information also
informs the pipeline shift, so these are internal residual checks, not an
independent held-out calibration. Gr11's wavelength-dependent error persists
at several slit positions and cannot be repaired by a single global shift.
Its recorded arc RMS is 0.851 Å from eight lines; the small fit RMS does not
establish accuracy between the fitted lines. Gr13 records 0.0147 Å from ten.

The automatic apertures are at spatial pixels **80.03** (AT2024afzf) and
**755.54** (AT2026agwm), whereas the plotted spatial profiles show a prominent
central trace. These are suspicious selections, not verified transient
identifications. Confirm the target with the acquisition image/slit geometry
before editing and extracting it. Do not automatically substitute the brightest
trace. Four negative sigma values already occur in the Gr11 extracted product
(zero-based pixels 163, 164, 845, 846); the telluric fix correctly scales the
input uncertainty but cannot make that extraction scientifically valid.

Independent-standard flux transfer calibrates L745a with vma2's response and
compares it to the repository's L745a AB-magnitude reference. The AB-to-flux
conversion uses `10**(-0.4*(AB+48.6))*c_A/lambda**2`. Fixed diagnostic windows
are 4500–4800, 5100–5500, 6000–6200 and 8000–8400 Å when covered. Their median
flux/reference ratios span 0.980–1.002 (Gr11), 0.929–1.025 (Gr13), and
0.997–1.083 (Gr16). L745a's own response is shown separately as a self-check.
The comparisons use uncorrected-for-telluric calibrated spectra, so the deep
atmospheric troughs are expected. Gr13 transfer uses the uncombined Free
responses; it does not validate second-order correction. Slit losses,
transparency, extinction and response shape all contribute; these ratios do
not establish absolute-flux accuracy.

Both final science FITS spectra are finite and agree with their ASCII exports.
Telluric sigma scales consistently with flux in both. The invalid Gr11 sigma
and source/calibration issues keep `scientific_acceptance` false. Eleven
regression tests and `pip check` pass. No raw files were edited, no products
were uploaded, and no commit or push was made.

## Evidence and repeat commands

All paths below are relative to the repository root:

- `runs/pyraf-debug/editor-05/editor-events.json`: Tk events, saved database,
  extraction shape and hashes.
- `runs/pyraf-debug/multisetup2d-02/verification.json`: exact 52-file raw inventory.
- `runs/pyraf-debug/multisetup1d-06/verification.json`: final science reduction.
- `runs/pyraf-debug/standards1d-02/verification.json`: all seven standard exposures.
- `runs/pyraf-debug/science-03/validation.json`: numerical diagnostics and provenance.
- `runs/pyraf-debug/science-03/{standard_transfer,sky_residuals,automatic_apertures}.{pdf,jpg}`:
  inspected SciencePlots/LaTeX/Hiroshige figures, with CSV transfer curves alongside.
- `runs/pyraf-debug/wcs-cache-probe/result.json`: minimal stale-header reproduction.
- `runs/pyraf-debug/tests-final.log` and `environment-freeze-current.txt`: test/runtime record.

Failed intermediate trials are retained for diagnosis; use the final paths
above. Runs are ignored by Git and remain local artifacts. The test scripts,
style helper, constraints and this report are the reproducible implementation.

```sh
cd /Users/avinash/Work/Reduction/pessto
.venv-pyraf/bin/python -m pip install -c constraints-pyraf.txt SciencePlots pypalettes
.venv-pyraf/bin/python scripts/validate_iraf_editor.py \
  --output runs/pyraf-debug/NEW-editor
.venv-pyraf/bin/python scripts/validate_science.py \
  --standards runs/pyraf-debug/standards1d-02 \
  --science runs/pyraf-debug/multisetup1d-06 \
  --output runs/pyraf-debug/NEW-science
.venv-pyraf/bin/pytest tests -q
```

For a physical mouse/keyboard check, open a terminal in a disposable editor
trial, activate this repository's environment, unset `PYRAF_NO_DISPLAY`,
and start `pyraf`. Load `noao`, `twodspec`, `apextract`, set `dispaxis=2`, then
run `apedit` on the copied vma2 image with `find=no recenter=no resize=no
interactive=yes line=200`. Exercise the keys above, answer the write prompt,
then re-open to confirm persistence. This human check and DS9 interaction
remain separate from the completed automated Tk test.
