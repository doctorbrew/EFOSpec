# WISeREP delivery packages

**Implemented:** `scripts/package_wiserep.py` creates separate public/private
ZIPs from explicitly reviewed EFOSpec flux products. It runs offline and never
uploads, sends mail, changes source data or assigns access from target names.

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

Complete each spectrum's manifest entry:

| Field | Required value |
| --- | --- |
| `object` | Exact reviewed FITS `OBJECT`; correct identity upstream if necessary. Preserve the full survey/TNS name, including punctuation. |
| `observers`, `reducers` | Full names, comma separated; no guessed attribution. |
| `reviewer`, `review_notes` | Who checked the product and the remaining limitations. These notes travel with the spectrum. |
| `reduction_date` | Actual UTC reduction time, `YYYY-MM-DDTHH:MM:SS`; not the packaging time. |
| `source_group` | Actual WISeREP source group name. |
| `spectrum_type` | `Object`, `Host`, `Sky` or `Arcs`; the initialization default `Object` must be checked. The exporter itself accepts only the supported calibrated EFOSpec product format. |
| `quality` | `Rapid`, `Final`, `Low`, `Med` or `High`, consistent with source `QUALITY`. Packaging does not promote rapid/experimental data to final quality. |
| `identity_reviewed`, `wavelength_reviewed`, `flux_reviewed`, `release_authorized` | Set each to `true` only after reviewing this exact hashed product and its intended recipients. |
| `visibility` | Explicit `public` or `private`. Public classification versus private follow-up is a review decision, never inferred from SN/AT or an OB name. |
| `associated_groups`, `proprietary_until` | Private: nonempty group-name list and future UTC end time. Public: `[]` and `null`. |
| `iau_name`, `object_type_id`, `redshift`, `host` | Optional reviewed information. Leave `null` when unknown; do not infer classification or redshift from a candidate fit. Type IDs refer to the legacy PESSTOWISE vocabulary, not a verified current API enumeration. |
| `publish`, `contrib` | Optional publication/contribution text, if established. |

`related_files` optionally contains up to two explicitly reviewed attachments,
matching the legacy table's two related-file columns. Use `role: "2d"` for an
associated calibrated 2D FITS product or `role: "plot"` for PNG/JPG/PDF/PS plots:

```json
{"path": "relative/to/manifest/target_2df.fits", "role": "2d", "sha256": "EXACT_SHA256"}
```

Calculate an attachment hash with `shasum -a 256 PATH`. Confirm its exposure,
revision and access class yourself; no filename-based attachment discovery is
performed. Attachments are copied byte-for-byte. Do not attach a whole nightly
report containing other targets to an individual public spectrum.

## Output and headers

The destination contains `public/`, `private/` and
`efospec_2026-11-10_upload_public.zip` /
`efospec_2026-11-10_upload_private.zip`. An unused class is omitted. Each ZIP has
its own flat file layout and contains only its selected spectra and attachments:

- Original FITS basenames, with all four scientific bands and `VALID` masks
  preserved. Delivery copies add `OBSERVER`, `REDUCER`, `DATE-RED`, `TELESCOP`,
  `PESSTO ACCESS`, `EFOSPEC NIGHT` and descriptive `WISEREP …` HIERARCH cards.
  Private copies record their associated groups and embargo end time. These
  cards are handoff instructions, **not archive-enforced access controls**.
- Header-free two-column `.asci` spectra: air wavelength in Angstrom and physical
  flux density in erg s⁻¹ cm⁻² Å⁻¹, coefficient **1**, topocentric observed frame.
  Do not apply another vacuum/air conversion, redshift correction or scaling.
  Samples with invalid primary flux/error masks or nonfinite/nonpositive sigma
  are omitted. Negative valid flux is retained; no interpolation is performed.
- Separate three-column `-errors.txt` files with statistical sigma in the same
  flux units. The two-column files are the spectrum ingestion files.
- Per-spectrum `-metadata.json` with review, correction/status provenance,
  omitted-sample counts and hashes; `access.json` lists that ZIP's access settings.
- `pesstowise-metadata.tsv`, `README.txt` and `SHA256SUMS`.

The exporter checks FITS structure/checksums, linear wavelength units/grid,
observation time/MJD agreement, coordinates, positive exposure time, physical
flux units and the selected file hashes. Failed calibration flags, provisional
products, count-only spectra, ambiguous visibility, changed inputs and duplicate
archive names are rejected. Weak but valid reviewed spectra can retain `Low` or
`Rapid` quality. No silent skipping occurs: a failure leaves no delivery directory.
Original sources are checked again before the completed directory is exposed.

## Ingest into WISeREP

Unzip one access class at a time. Use the Report form to select the exact object,
upload its `.asci`/FITS files, check observation metadata, select ESO-NTT / EFOSC2,
and set the units and wavelength medium above. Check actual extinction/telluric
history in the FITS/JSON; packaging adds no corrections. Associate related files
with the corresponding spectrum. Set source group, proprietary period and
associated groups explicitly, checking both report-level and spectrum-level
settings before submission. Public and private batches must stay separate.

The ZIPs are also suitable for handing the files and metadata to the authorized
WISeREP ingest team. Private ZIPs have restrictive local permissions but are not
encrypted; deliver them only to the intended recipients. They are not published
by the GitHub Pages workflow.

**Compatibility boundary:** the TSV uses the preserved **28-column PESSTOWISE
layout**, with one header row and one row per spectrum, without its old defaults
row. EFOSC's legacy instrument ID is `31`. It is a documented team handoff,
**not a claimed WISeREP v2 bulk-API or Report-form TSV payload**. Current WISeREP
supports form entry and its own TSV/JSON bulk schemas. Obtain and verify its
current template before using automated bulk ingestion. No network ingestion
acceptance test has been performed.

## Sources checked

- Supplied **PESSTO Handbook v1.39**, printed pp. 35–36, “Preparing quick
  reductions for ingest to WISEREP”: separate public classifications and private
  follow-up batches; include metadata and associated 2D/plot products; retain
  exact names and leave uncertain classifications/redshifts unknown.
- Supplied **ePESSTO NTT pipeline user manual draft**, “Preparing data for
  WISEREP”: `PESSTOWISE`, reviewed names/coordinates and observer/reducer names.
  Source PDF hashes are in [manual provenance](manual/source-hashes.json).
- Preserved [PESSTOWISE](../trunk/bin/PESSTOWISE): column order and EFOSC ID.
  The exporter keeps fractional exposure seconds and does not mislabel the
  filter as a grating.
- [WISeREP getting started](https://www.wiserep.org/content/wiserep-getting-started):
  Report form, bulk templates and group/proprietary controls. Checked
  2026-11-18 via the indexed official documentation; direct page access returned
  HTTP 403, so the current downloadable bulk template was not validated.

This is EFOSpec delivery packaging, not ESO Phase 3 certification or a port of
the IRAF-only input format. Legacy products without EFOSpec's masks still use
their preserved legacy workflow.
