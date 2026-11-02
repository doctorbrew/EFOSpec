# Approved Fieldnotes design

Baseline: the EFOSpec 2026-10-28 daily log, approved on 2026-11-02. The reusable renderer was introduced in [EFOSpec commit e688dfe](https://github.com/sPaMFouR/EFOSpec/commit/e688dfeb4c201da919f910d7a37326f1e38d0776). Within EFOSpec, its current renderer and shared CSS are authoritative; this reference supports reuse when those files are unavailable.

## Visual structure

- Quiet cream page, forest-green serif headings, neutral sans-serif table/body text, thin borders and restrained rounded corners. No dashboard sidebar, oversized metric cards or decorative hero illustration.
- `Fieldnotes. / EFOSpec` masthead; instrument and date opposite. Use the current project's name when explicitly adapting the design elsewhere.
- Prominent observing date, concise counts of spectra/failed/unsupported exposures, and one small line for reduction method, status and processing revision.
- Compact wrapping navigation above the log. Each item is a real `#section` anchor; every section remains visible in reading order.
- Main content up to 1480 px wide; desktop padding around 28–32 px, narrow-screen padding around 12–18 px. Data tables scroll within their own container rather than widening the whole page.

| Token | Approved value |
| --- | --- |
| Paper / panel | `#f7f6f0` / `#fffef9` |
| Forest / main ink | `#244d3d` / `#29362e` |
| Muted / divider | `#616a61` / `#dfe2d7` |
| Serif | Iowan Old Style, Palatino Linotype, Georgia, serif |
| Body | Avenir Next, Avenir, Helvetica Neue, Arial, sans-serif |
| Body size / leading | 15 px / 1.55 |
| Main / section / target headings | 38 / 27 / 22 px, regular weight |
| Figure cards | Thin divider, 8 px radius, white figure area |

Use installed font stacks rather than remote font dependencies. Scientific plot fonts and colours follow the plot style, independently of webpage typography.

## Sections, in order

| Section | Content |
| --- | --- |
| Observing log | Target, UTC start, science/standard role, setup, slit, seconds and recorded result. Spectrum links scroll to that exposure. No added source-selection control column. |
| Spectra | One article per reduced exposure: target/setup/slit, UTC timestamp, association caveat where applicable, FITS/ASCII downloads, then spectrum, 2D trace and spatial profile. |
| Issues | Recorded issue codes, exposure counts, affected targets and concise explanations. Preserve failed and unsupported categories. |
| Source QC | Exposure identity status, candidate raw detector positions, detector/trace profiles and available acquisition previews. |
| Background | Saved, exposure-specific recipe choices and diagnostics: left/right sampling bands outside the aperture, polynomial degree and valid support, with provisional identity and calibration limits where applicable. No automatic C3 selection. |
| Calibrations | Recorded grism/filter/slit groups, construction status and wavelength QA with units; distinguish diagnostics from calibrations actually applied to the displayed spectra. |
| Archive | Compact table of retained runs and outcomes. Do not merge old results into current totals. |
| Run record | Stage statuses/errors, downloadable logs/provenance and a short folder guide. |

Use concise availability text when a section has no evidence. Do not fabricate data to fill a card. Place the observing log first, and keep the subsequent figures and summaries visible rather than behind tabs or iframes.

## Figure and interaction behavior

- Three figure columns per spectrum on desktop; two columns for QC/background previews. Stack at narrow widths.
- Labels sit above each plot. Click/tap opens an in-page enlargement with an accessible Close button and Escape handling. No new window or external image route is necessary for viewing.
- Embed resized previews from existing plot files; keep original high-resolution scientific files unchanged. Downloads must decode to the original product bytes.
- Use embedded data URLs for portable images/downloads and inline CSS/JavaScript. Core content remains readable without JavaScript; scripts add enlargement only.
- No server, external CDN, remote font, `fetch()` dependency, absolute local asset URL or redirect is needed to read the final file.

Minor refinements may change spacing, wording or specific content without replacing this visual structure. Changes to scientific methods, source identity or background choices require their own evidence and task scope.
