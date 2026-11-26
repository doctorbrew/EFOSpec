# EFOSpec: from extraction to spectrum and nightly log

Run from the checkout in the dedicated EFOSpec environment. Process one observing
date at a time. The examples use **2026-11-25** and **AT2026afvu**. An exposure
after midnight can belong to the preceding observing night.

## Choose the next step

| What you have | What to do next |
| --- | --- |
| Raw exposures only | Run the dated reduction below. |
| Extracted counts with an accepted wavelength solution | Check the saved same-night response and flux-export result; do not repeat extraction just to refresh a page. |
| A flux-calibrated FITS already exists | Inspect its spectrum, masks and warnings; rebuild the HTML from saved results. |
| Counts exist but the sky-line validation failed | Review the wavelength evidence. An explicitly chosen provisional flux product can use the saved arc grid and matched response; it does not pass the failed wavelength check. |
| An older spectrum disappeared after a target-only run | Rebuild the report with this version. Unchanged earlier products stay in the main nightly log. |
| No extracted spectrum | Resolve source/background/calibration errors before attempting flux calibration. |

## Normal reduction

```sh
python scripts/reduce_epoch.py 2026-11-25
```

To rerun one target in a **new revision**:

```sh
python scripts/reduce_epoch.py 2026-11-25 --target AT2026afvu
```

The pipeline selects same-night standards and matching instrumental setups. A
Feige110 response from a different grism, filter or slit is not interchangeable.
The extraction uses the brightest positive source near the expected position
unless an exposure-bound reviewed selection takes precedence. Check the trace
and acquisition evidence: automatic extraction alone does not establish identity.

Keep finite background bands on both sides of the aperture: normally 30 pixels
per side, narrowing to 15 where needed, with widths up to 50 available. Review
contamination and overlap in the saved plots; do not replace this with a
one-sided fit or the remaining detector. Geometry changes belong in a new
revision through the [desktop workflow](desktop.md).

## Wavelength and flux checks are separate

The arc fit assigns wavelengths. Sky validation then checks whether that grid
agrees with the exposure. The current full-spectrum policy requires global
agreement and the **same two of three** sky regions to pass before and after
the correction. One weak region can warn; a failed global correlation cannot be
rescued by two good regions. Explicit older recipes retain their recorded policy.

Flux calibration applies the standard-star response to the extracted counts,
using the saved exposure and extinction information. It does not repair an
incorrect wavelength grid. If a matching response already exists, no extra
standard observation or manual flux scale is needed just to apply it. The
result still needs review for slit losses, host light and other systematics.

Inspect `reduction/run.json`, the exposure's `pending_checks`, and its error log
to distinguish a missing response from withheld flux due to a wavelength check.
“Flux calibration pending” alone is not a diagnosis.

## Apply provisional flux to saved wavelength-review counts

Use this only when a provisional product is explicitly wanted. It requires
successful extraction, acceptable two-sided background support, unchanged inputs
and a matching saved response. It reuses counts and **unshifted arc wavelengths**;
it neither reruns the extraction nor converts a failed wavelength check into a
pass. Products remain `PROVISIONAL`, with absolute flux unvalidated.

Read `runs/2026-11-25/efospec/nightly/current.json` for the selected revision.
Replace `REVISION` below, and choose a fresh rescue directory for each attempt:

```sh
python -m efospec rescue-daily \
  runs/2026-11-25/efospec/nightly/REVISION/reduction \
  --night 2026-11-25 --target AT2026afvu \
  --output runs/2026-11-25/efospec/rescue/AT2026afvu-flux-NEW \
  --skip-report

python scripts/verify_rescue_reduction.py \
  runs/2026-11-25/efospec/rescue/AT2026afvu-flux-NEW

python scripts/preview_spectrum_style.py \
  --run runs/2026-11-25/efospec/rescue/AT2026afvu-flux-NEW \
  --target AT2026afvu --no-legacy
```

Check that the rescue has the requested spectrum, no errors and a passing audit.
To select that audited rescue for the nightly HTML, preserve the previous
selection and write the hash-bound pointer:

```python
from datetime import datetime, timezone
import json
from pathlib import Path
from efospec.inventory import sha256

root = Path('runs/2026-11-25/efospec').resolve()
rescue = root / 'rescue/AT2026afvu-flux-NEW'
run = json.loads((rescue / 'run.json').read_text())
audit = json.loads((rescue / 'verification.json').read_text())
current = json.loads((root / 'nightly/current.json').read_text())
parent = root / 'nightly' / current['revision'] / 'reduction/run.json'
assert run['night'] == current['night'] == '2026-11-25'
assert run['results'] and not run['errors']
assert run['parent_sha256'] == sha256(parent)
assert audit['status'] == 'passed'
assert audit['run_sha256'] == sha256(rescue / 'run.json')
pointer = root / 'rescue/current.json'
if pointer.exists():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    pointer.with_name(f'previous-{stamp}.json').write_bytes(pointer.read_bytes())
pointer.write_text(json.dumps(dict(
    night=run['night'], path=str(rescue.relative_to(root)),
    run_sha256=sha256(rescue / 'run.json')), indent=2) + '\n')
```

The AT2026afvu example illustrates the distinction: Feige110 supplied the flux
response, but the science exposure's global sky correlation failed. Applying
the response produced a useful provisional spectrum, not a newly validated
wavelength solution. Do not relabel it `Final` merely because flux units exist.

## Keep the nightly HTML current

After changing a selected product or saved diagnostic, rebuild presentation only:

```sh
python -m efospec.epoch_report 2026-11-25
```

- Open `runs/2026-11-25/efospec/index.html`. For a new in-app link, use the
  returned `viewer_path`, `index-view-<hash>.html`, to avoid an old cached page.
- Every new report includes unchanged earlier same-night FITS/ASCII products,
  spectrum/trace/profile plots and original warnings. They appear in the main
  log, not just the Reduction Archive. This is a standing workflow rule.
- A newer attempt takes precedence, including failures. A changed raw identity
  or a missing/mismatched product checksum prevents automatic reuse and is
  reported. “Outside selected targets” was a selection label, not an extraction
  failure; it must not hide an existing unchanged spectrum.
- `report-products.json` remembers displayed selections, including adopted
  recoveries. Keep its referenced revisions and products; report assembly does
  not copy them into a new scientific reduction or recompute them.
- Keep `report-assets/` beside the HTML for downloads. Use `index-portable.html`
  when a single self-contained offline file is needed.
- A report-only rebuild does not regenerate figures. For a selected saved run,
  use `preview_spectrum_style.py --run RUN --target NAME --no-legacy` when figures
  actually need refreshing, then rebuild the report. Archive earlier diagnostics
  before a full figure refresh; `--profiles-only` archives profile revisions.
- Extraction plots should share the Feige110 orientation and style: paired
  wavelength-horizontal before/after panels, red aperture shading and blue
  background regions. Use the canonical house-style renderer, LaTeX, enlarged
  inward ticks, and PDF plus 300-dpi JPG. Reuse existing figures for unchanged
  spectra rather than redrawing them during report assembly.

## Potential host redshift

Host-line measurement is a separate step; refreshing HTML alone does not run it.
Use a fresh output directory in the selected revision:

```sh
python scripts/measure_host_redshifts.py 2026-11-25 \
  --output runs/2026-11-25/efospec/nightly/REVISION/QC/redshifts-NEW \
  --update-report
```

The saved selection is bound to its parent products. NED associations and
spectral measurements remain separate. Insufficient matching lines means no
redshift measurement, not zero redshift. This command measures its selected
current products; carrying older spectra into the HTML does not by itself
remeasure their hosts or validate an old redshift against a new extraction.

## Before delivering a spectrum

- Check source identity, aperture, both background bands, wavelength status,
  response setup, valid-pixel coverage and the extracted spectrum.
- Keep masks, uncertainties, units, wavelength medium and provenance. Saved
  plots are inspection aids; the FITS and its validity information remain the
  scientific product.
- Preserve provisional/review labels. Use the [WISeREP delivery guide](wiserep-delivery.md)
  for eligible reviewed products; preparing a file is separate from uploading it.
- See the [epoch workflow](epoch-workflow.md) for the full dated layout and
  [same-night standard calibration](daily-standard-calibration.md) for response details.
