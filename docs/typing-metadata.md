# Host association and adopted redshift

EFOSpec edits annotations separately from reduction and classification. The
selected reduction's `typing-metadata.json` follows Spectypus's
`efospec-typing-metadata/1` contract. Saved metadata does not change a completed fit.

## Desktop

Open `efospec gui runs/2026-10-28` and choose **Host & redshift**.

- Select the exact science spectrum. Edit the host, separation in arcseconds,
  redshift, uncertainty, method, reference frame and catalogue reference.
- Candidate galaxies and provenance are editable JSON lists. Keep full catalogue
  records, alternative candidates and measurement references; the closest galaxy
  is never selected or accepted automatically.
- Choose `host_catalogue`, `narrow_lines` or `transient_spectral` for an adopted z.
  Catalogue adoption requires an accepted host and identical host/adopted z.
- Enter the reviewer identity and explicitly check the host/redshift acceptance
  boxes. Saving an accepted field change requires renewed acceptance. UTC review
  times are recorded separately for host, redshift and metadata edits.
- **Save metadata revision** writes annotations only. **Refresh nightly HTML**
  then renders compact tags below acquisition plots and a bottom verification
  section without running
  reduction, plotting, catalogue queries or classification.
- To withdraw adoption, clear adopted z and change redshift status. To withdraw a
  catalogue host, also withdraw its adopted z or adopt a separately reviewed source.
- Blank uncertainty, frame or method remains unknown; zero redshift is valid.
  Unaccepted redshift measurements belong in the candidate/provenance lists,
  rather than `adopted_redshift`.
- Enter a spectrum URL only for a genuine published product. Without one the
  existing local FITS/ASCII download remains available; no URL is fabricated.

## CLI

```sh
# Inspect without writing (also supplies a full editable document):
efospec typing-metadata show runs/2026-10-28
# Initialize unreviewed records, preserving the reduction and spectra:
efospec typing-metadata init runs/2026-10-28 --reviewer 'Reviewer identity'
# Example candidate annotation; values below are placeholders, not identifications:
efospec typing-metadata edit runs/2026-10-28 \
  --spectrum EXACT_SPECTRUM.asci --reviewer 'Reviewer identity' \
  --set 'host_status=candidate' --set 'host_name=Reviewed galaxy name' \
  --set 'host_source=Catalogue record/reference' --candidates candidates.json
# Refresh the current dated HTML from saved data:
efospec typing-metadata report runs/2026-10-28
```

- `--set FIELD=VALUE` accepts a JSON value or plain text; `null` clears an
  optional value. `--accept-host` and `--accept-redshift` explicitly accept the
  selected spectrum's association and adopted z respectively.
- Set `host_redshift`, `host_redshift_uncertainty`, `host_redshift_method`,
  `host_reference_frame`, `host_separation_arcsec`, `adopted_redshift`,
  `adopted_redshift_uncertainty`, `adopted_redshift_kind`,
  `adopted_redshift_source`, `adopted_redshift_method` and
  `adopted_redshift_reference_frame` as applicable.
- `--input edited.json` reads a full document previously emitted by `show`.
  Keep its reduction identity, spectrum identities/hashes and revision ID.
  Accepted changes still need the explicit flags and `--spectrum` selection.
- `--evidence PATH/redshifts.json` imports saved line/catalogue measurements only
  when their parent manifest matches this exact reduction. It retains every NED
  candidate and the complete measurement record without accepting a host or z.
- Changed spectra, mismatched objects, copied older-reduction metadata and stale
  editor revisions fail before saving. An old `redshifts.json` cannot be rebound
  by importing it into a newer reduction.

## Storage and provenance

- `reduction/run.json` and the original FITS/ASCII products are unchanged.
- `reduction/typing-metadata.json` is the current Spectypus export, with the
  reduction SHA256, per-ASCII SHA256, exact object identity, candidate evidence,
  accepted fields and reviewer identity/time.
- `reduction/typing-metadata-revisions/*.json` retains immutable full snapshots;
  the current export is replaced atomically. Concurrent saves are rejected.
- The HTML uses this same validated export and includes a JSON download and
  expandable complete evidence in **Host verification** at the bottom. Empty
  initialization fields are hidden, and spectrum panels contain no host blocks.
  Stale metadata stops rendering;
  it is never presented as current.
- Metadata belongs to one selected science spectrum in one reduction. Rescue
  products and older reductions are not silently merged or promoted.
- This implementation binds the absolute manifest path as well as its hash;
  relocation needs a deliberate provenance review, not automatic hash rebinding.

The consumer contract is **“EFOSpec typing metadata”** in the adjacent
Spectypus checkout's `docs/USAGE.md`. Its reader is exercised in the local
2026-10-28 validation; no classification is run.

## Validation on 2026-10-28

- Selected reduction: `nightly/20261110T170405Z-b97078/reduction`.
- Exported four science-spectrum records, all unreviewed. No genuine published
  spectrum URL was recorded in these reduction results, so local downloads remain.
- The saved `QC/host-redshifts-20261109-v4/redshifts.json` belongs to an older
  reduction; import was rejected, and the exclusion reason/reference was retained.
  Its old galaxy/line measurements were not adopted or relabelled as current.
- All 504 protected reduction manifests, products and selection files were
  hash-identical after export and HTML refresh. No real reduction or classification
  ran. Previous opening reports remain in `archive/before-typing-metadata-20261111`.
- Direct checks against Spectypus's implemented reader passed for this export,
  synthetic examples of all three accepted kinds, candidate non-adoption and stale
  metadata rejection. Native macOS Cocoa launch opened all three tabs successfully.
- Retained local evidence: `outputs/typing-metadata-validation-2026-10-28/`.

## Proposed cross-matches in the nightly log

On 2026-11-11, fresh NED queries at the named observing-block target coordinates
were compared with public TNS records. These queries are bound to the selected
reduction; the older line-measurement revision remains excluded.

| Target | Preferred cross-match for verification | Evidence / limitation |
| --- | --- | --- |
| AT2026agwm | ESO 339- G 013 | 2.86 arcsec; spectroscopic catalogue z=0.020404 agrees with [ePESSTO+ AstroNote 2026-300](https://www.wis-tns.org/astronotes/astronote/2026-300). |
| SN2026aebl | SDSS J004353.77-040920.1 | 28.75 arcsec; spectroscopic z=0.0232399 is broadly consistent with the [published narrow-line z=0.0224](https://www.wis-tns.org/object/2026aebl). Association remains ambiguous: nearer MCG -01-03-004 has photometric z=0.074716 and is retained for comparison. |
| AT2024afzf | WISEA J073235.28-171815.6 | Positional counterpart only, 0.90 arcsec from the OB position. [ePESSTO+ AstroNote 2025-33](https://www.wis-tns.org/astronotes/astronote/2025-33) describes a likely Galactic transient; no galaxy host assigned. |
| AT2026aeul | WISEA J022243.26-473303.5 | Coincident NED galaxy, 0.20 arcsec; catalogue z unavailable. The published z=0.073 is from transient template matching, not the host. |

- `preferred_crossmatch` retains the chosen record, separation, coordinate basis,
  rationale and caveat. `host_candidates` preserves galaxy alternatives;
  `catalogue_sources` also retains unclassified positional neighbours.
- `redshift_candidates` keeps published narrow-line/template estimates separate
  from `host_redshift` and accepted `adopted_redshift`.
- Tags link to bottom-of-page verification with NED, TNS, supporting reports and
  the PESSTO Marshall portal. Marshall requires login and is a portal link, not
  an invented object URL. Catalogue cards without a saved acquisition plot still
  show the proposal beside their existing unavailable-astrometry notice.
- These are explicit proposals, not automatic nearest-galaxy acceptances.
  No accepted host or adopted redshift was introduced. No reduction or fit ran.
- Query responses, selection script, previous reports and validation are retained
  under `runs/2026-10-28/QC/typing-crossmatch-20261111/`.
