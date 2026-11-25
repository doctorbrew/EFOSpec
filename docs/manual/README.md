# Reduction Manual sources

Open [manual_pessto.html](../../manual_pessto.html) at the repository root.
It contains environment startup and troubleshooting, all three workflows,
delivery instructions, embedded figures and the frame-list download.

The current installed Mac runtime uses `conda activate pessto` for PyRAF and
`conda activate efospec` for PypeIt. The pessto activation hook supplies the
lowercase IRAF path; the historical `.venv-pyraf` activation is not a routine
startup step. Keep both IRAF workflow entries consistent with the shared
environment section in `guide-content.html`.

From the repository root, rebuild it with:

```sh
conda activate efospec
python scripts/build_manual.py
```

Edit `guide-content.html` and `guide.css` here. Figure hashes and provenance
remain alongside the figures; `verification.json` records the original dated
review, not a claim that every later revision was browser-tested.
The original supplied PDFs are retained privately and identified by source hashes.
IRAF preparation and list helpers live in `scripts/`.
After editing, rebuild the root HTML, check internal anchors and embedded
downloads, and verify command examples against the installed entry points.
Do not regenerate scientific figures for a prose-only manual update.
