# WISeREP delivery packages

**Implemented:** the nightly log's **Science delivery** section and
`scripts/package_wiserep.py` create separate public/private
PESSTOWISE `.tgz` tarballs from explicitly reviewed EFOSpec flux products. It runs
offline and never uploads, sends mail, changes source data or assigns access from
target names.

## Export from the observing log

Open `runs/YYYY-MM-DD/efosc/index.html` or its portable HTML copy. Newly generated
reports include **Science delivery** immediately below the observing log. The
[2026-11-10 published log](https://doctorbrew.github.io/EFOSpec/2026-11-10/#delivery)
also includes these controls.

1. Select **Public** or **Private** for each reviewed target. **Do not export** is
   the default; targets without an eligible flux product are disabled. Every
   eligible setup listed for a target goes into its chosen archive. Check the
   **Object / Host** spectrum type, especially for host-galaxy extractions.
2. In **Observer / reducer names and delivery details**, enter observer and
   reducer names and the actual UTC reduction date (`YYYY-MM-DD`). Source group
   and private associated groups are prefilled with **ePESSTO+**, and remain
   editable for another collaboration. For private selections, enter a future
   UTC embargo end. FITS header text uses ASCII; spell accented names in ASCII.
3. Confirm the review, then click **Prepare public / private tarballs**. Download
   the separate public/private links. Only populated classes produce a file.

Names and reduction date are written into `OBSERVER`, `REDUCER`, `DATE-RED` and
the matching upload-table columns. Spectrum type, source group, access and private
embargo/group information are recorded in FITS. Source quality and scientific
arrays are preserved; checksums are recalculated. No names or access choices are
saved in the HTML or sent to a server; reloading clears them. Changing a choice or
field removes old download links until the archives are prepared again.
Reloading or **Clear choices and names** restores the two group defaults to
**ePESSTO+**. Prefilled private groups are ignored for public exports.

The report builder uses the same Python science validation and primary-FITS
conversion as the CLI. The browser assembles the archives offline from those saved
payloads. It includes eligible science spectra only, excludes standard stars,
count-only and failed calibration products, and adds no plots or calibrated 2D
attachments automatically. Use the CLI below for reviewed attachments, per-spectrum
attribution, optional classification/redshift metadata and a persistent audit record.
The browser uses the same table preamble, flat tar layout and valid-pixel ASCII
convention as the CLI; it uses gzip stored blocks for compatibility without an
external compression library. Keep the original full masked FITS for science.

**Private describes the requested archive access.** It does not restrict access
to the HTML log or encrypt downloaded files. A public GitHub Pages report already
exposes its included science products; keep reports containing unpublished spectra
local or on access-controlled hosting. The ingest team applies server permissions.

## Prepare one observing night

Activate the installed `efospec` environment and run from the repository root.
Select the accepted `_f.fits` files from the exact reduction revision, not a
recursive glob over older reductions, failed extractions and standard stars.

```sh
python scripts/package_wiserep.py init 2026-11-10 \
  runs/2026-11-10/efosc/nightly/REVISION/reduction/products/SELECTED_f.fits \
  --output runs/2026-11-10/efosc/delivery-review.json

# Edit delivery-review.json and complete the review below, then:
python scripts/package_wiserep.py build \
  runs/2026-11-10/efosc/delivery-review.json \
  runs/2026-11-10/efosc/delivery/review-001
```

Both commands also work as `python -m efospec.wiserep init …` / `build …`.
Initialization records exact paths, SHA-256 hashes, object names and source
quality. It leaves visibility unset and all review/release flags false. Neither
command overwrites an existing manifest or delivery directory. The night is the
start date of the observing night; exposure UTC dates must be that date or the
following day. Each invocation handles one night.

New manifests prefill `source_group: "ePESSTO+"` and include
`private_defaults: {"associated_groups": ["ePESSTO+"]}`. A private spectrum with
an empty or missing `associated_groups` inherits that manifest default; a nonempty
per-spectrum list overrides it. Public spectra never inherit private groups.
Older manifests without `private_defaults` still require an explicit private
group list. No embargo date is inferred.

Complete each spectrum's manifest entry:

| Field | Required value |
| --- | --- |
| `object` | Exact reviewed FITS `OBJECT`; correct identity upstream if necessary. Preserve the full survey/TNS name, including punctuation. |
| `observers`, `reducers` | Full names, comma separated; no guessed attribution. |
| `reviewer`, `review_notes` | Who checked the product and the remaining limitations. These notes travel with the spectrum. |
| `reduction_date` | Actual UTC reduction time, `YYYY-MM-DDTHH:MM:SS`; not the packaging time. |
| `source_group` | Defaults to `ePESSTO+`; editable for another collaboration. |
| `spectrum_type` | `Object`, `Host`, `Sky` or `Arcs`; the initialization default `Object` must be checked. The exporter itself accepts only the supported calibrated EFOSpec product format. |
| `quality` | `Rapid`, `Final`, `Low`, `Med` or `High`, consistent with source `QUALITY`. Packaging does not promote rapid/experimental data to final quality. |
| `identity_reviewed`, `wavelength_reviewed`, `flux_reviewed`, `release_authorized` | Set each to `true` only after reviewing this exact hashed product and its intended recipients. |
| `visibility` | Explicit `public` or `private`. Public classification versus private follow-up is a review decision, never inferred from SN/AT or an OB name. |
| `associated_groups`, `proprietary_until` | Private: group-name list (or inherit the manifest's private default) and future UTC end time. Public: `[]` and `null`. |
| `iau_name`, `object_type_id`, `redshift`, `host` | Optional reviewed information. Leave `null` when unknown; do not infer classification or redshift from a candidate fit. Type IDs refer to the legacy PESSTOWISE vocabulary, not a verified current API enumeration. |
| `publish`, `contrib` | Optional publication/contribution text, if established. |

`related_files` optionally contains up to two explicitly reviewed attachments,
matching the legacy table's two related-file columns (one plot and one 2D image).
Use `role: "2d"` for an associated calibrated 2D FITS product or `role: "plot"`
for PNG/JPG/PDF/PS plots:

```json
{"path": "relative/to/manifest/target_2df.fits", "role": "2d", "sha256": "EXACT_SHA256"}
```

Calculate an attachment hash with `shasum -a 256 PATH`. Confirm its exposure,
revision and access class yourself; no filename-based attachment discovery is
performed. Attachments are copied byte-for-byte. Do not attach a whole nightly
report containing other targets to an individual public spectrum.

## Output and headers

The default output is two gzip-compressed tar archives, for the populated classes:

```text
pessto_YYYYMMDD_HH_MM_Rapid_upload_public.tgz
pessto_YYYYMMDD_HH_MM_Rapid_upload_private.tgz
```

The timestamp is UTC **packaging time**, as in the reference filenames, not the
observing-night date. Each spectrum retains its actual `DATE-OBS`. `Rapid` is the
reviewed quality; each access class must have one quality, otherwise use separate
manifests. `--timestamp 2026-11-18T14:03:00` optionally fixes the filename stamp.
An unused access class is omitted. There is no automatic public/private inference.

The upload archives contain **only** these flat, referenced files:

- `pessto_YYYYMMDD_HH_MM_Rapid_upload.txt`: exact 28-column header (including the
  old trailing space in the Quality label), the exact **21-field defaults line**,
  then 28 tab-separated fields per spectrum. Do not pad or delete that defaults
  line: all four supplied examples use it. Missing optional fields use `NULL`;
  unknown object type uses the legacy code `0`.
- Original `_f.fits` basenames: **one primary HDU**, four bands shaped `(4, 1, N)`.
  Science values, binning, extraction labels, flux units and air/topocentric
  wavelengths are retained. Delivery copies add observer/reducer attribution,
  reduction time and access instructions, plus legacy `CD1_1`, `WCSDIM` and
  `WAT*` wavelength descriptors. The legacy `BUNIT` spelling is
  `erg/cm2/s/Angstrom`. No IRAF aperture coordinates or extraction claims are
  fabricated; `BANDID*` continues to describe the actual PypeIt extraction.
- Header-free, **tab-separated** two-column `.asci` spectra: air Angstrom and
  erg s⁻¹ cm⁻² Å⁻¹, coefficient **1**, topocentric observed frame. Invalid
  primary flux/error samples are omitted, with no interpolation or rescaling.
  Negative valid flux remains. The wavelength grid and sample count need not
  equal the older IRAF examples; their numerical values are preserved.
- Explicit optional attachments: plot in `Related-file1`, calibrated 2D image in
  `Related-file2`, or `NULL`. A native PypeIt multi-extension `spec2d` is not a
  legacy flux-calibrated `_2df.fits` and is rejected for that slot.

For exact compatibility, the table's historically labelled **Grating** column
contains the **filter** (`Free`, `OG530`, etc.), as in the supplied archives.
Exposure time in that table uses legacy integer seconds; FITS retains the full
precision. Observation UT uses milliseconds, and reduction date is a UTC date;
full reduction time stays in FITS/local JSON. No object classification or redshift
is inferred. These conventions are specific to the collaborators' legacy format.

The local `public/` and `private/` audit folders retain full FITS copies including
`VALID` masks, error sidecars, per-spectrum JSON, access instructions and hashes.
Both native `(4, N)` and singleton-aperture `(4, 1, N)` mask layouts are supported.
The primary-only FITS copies **inside the TGZ** omit the mask extension for legacy
reader compatibility; always retain the audit/source products for further science.
JSON, error text, README and checksum files do not go inside the upload TGZ, so
there is exactly one `.txt` metadata file. macOS `._*` files are not generated.

## Validate and share

```sh
python scripts/package_wiserep.py validate \
  runs/2026-11-10/efosc/delivery/review-001/*.tgz

# Optional: verify the supplied reference examples locally
python scripts/package_wiserep.py validate wiserep_tns_upload/*.tgz
```

`build` runs the same validator before exposing the output directory. It checks
the metadata preamble, column count, unique flat members, all referenced files,
primary FITS structure/units/checksums, and ASCII wavelength/flux agreement with
the FITS primary spectrum. The validator reads without extracting. For the
original examples it ignores AppleDouble `._*` files. A failure leaves no delivery
directory, and source hashes are checked again before completion.

The scientific review checks also reject failed calibration flags, provisional
or count-only products, inconsistent date/MJD, invalid coordinates/units, changed
inputs and ambiguous access. Weak but valid reviewed spectra can retain `Low` or
`Rapid` quality. Packaging does not upgrade their scientific status.

Send each tarball to its intended collaborators for their existing PESSTOWISE
server-ingestion workflow. If inspecting both archives, extract them into separate
directories: the public/private tarballs can contain the same metadata filename.
CLI private archives have restrictive local permissions but are not encrypted. Access
cards in FITS are instructions; the ingest team still applies archive permissions.
Generated delivery archives and the supplied reference tarballs are not published
by GitHub Pages. Published observing logs include their selected science products.

**Verified locally:** all four supplied TGZs (15 spectra) and conversion of the
current 2026-11-10 PypeIt-derived flux products. This establishes file-format and
numerical compatibility, not a completed remote-server upload or science release.
These tarballs are not a TNS classification API request or a WISeREP v2 JSON
payload. No upload is performed by this script.

The earlier collaborator ZIP layout remains available with `build … --format zip`.
It keeps full masked FITS and audit sidecars inside ZIPs, with its earlier
single-header TSV. Use the default TGZ mode for the supplied server-ingest format.

## Sources checked

- **Group defaults:** the supplied handbook identifies the programme as
  **ePESSTO+** on p. 1. Its ingest instructions on pp. 35–36 prescribe separate
  public/private tarballs but do not state WISeREP group-field values or an
  embargo duration; neither do the four example tarballs. The exact spelling
  **ePESSTO+** is corroborated by WISeREP's
  [source-group record](https://www.wiserep.org/form-edit/spectrum/62438) and
  [EFOSC2 spectrum with source and associated group ePESSTO+](https://www.wiserep.org/object/28770).
  Checked 2026-11-18. We use that collaboration as the editable default for this
  workflow; this is not a statement about the uploader account's permissions.
- Supplied **PESSTO Handbook v1.39**, printed pp. 35–36, “Preparing quick
  reductions for ingest to WISEREP”: separate public classifications and private
  follow-up batches; include metadata and associated 2D/plot products; retain
  exact names and leave uncertain classifications/redshifts unknown.
- Supplied **ePESSTO NTT pipeline user manual draft**, “Preparing data for
  WISEREP”: `PESSTOWISE`, reviewed names/coordinates and observer/reducer names.
  Source PDF hashes are in [manual provenance](manual/source-hashes.json).
- Four local `wiserep_tns_upload/pessto_20261028_*.tgz` and
  `pessto_20261029_*.tgz` examples: archive membership, exact two-line metadata
  preamble, column conventions, FITS structure and numerical ASCII agreement.
  They remain local/Git-ignored; only the non-scientific header/defaults fixture
  is tracked for regression checks.
- Preserved [PESSTOWISE](../trunk/bin/PESSTOWISE): column order and EFOSC ID.
  TGZ deliberately reproduces its integer exposure seconds and legacy
  filter-in-Grating convention; physical metadata remains explicit in FITS.
- [WISeREP getting started](https://www.wiserep.org/content/wiserep-getting-started):
  Report form, bulk templates and group/proprietary controls. Checked
  2026-11-18 via the indexed official documentation; direct page access returned
  HTTP 403, so the current downloadable bulk template was not validated.

This is EFOSpec delivery packaging, not ESO Phase 3 certification or a port of
the IRAF-only input format. Legacy products without EFOSpec's masks still use
their preserved legacy workflow.
