# Reduction Manual sources

Open [manual_pessto.html](../../manual_pessto.html) at the repository root.
It contains all three workflows, embedded figures and the frame-list download.

From the repository root, rebuild it with:

```sh
python scripts/build_manual.py
```

Edit `guide-content.html` and `guide.css` here. Figure hashes and provenance
remain alongside the figures; `verification.json` records the original dated
review, not a claim that every later revision was browser-tested.
The original supplied PDFs are retained privately and identified by source hashes.
IRAF preparation and list helpers live in `scripts/`.
