# pdf.js provenance

- Upstream project: https://github.com/mozilla/pdf.js
- Version vendored: **v6.3.289**
- Release page: https://github.com/mozilla/pdf.js/releases/tag/v6.3.289
- Artefact downloaded: `pdfjs-6.3.289-legacy-dist.zip`
  (https://github.com/mozilla/pdf.js/releases/download/v6.3.289/pdfjs-6.3.289-legacy-dist.zip)
- Files taken from the artefact's `build/` directory only:
  - `build/pdf.mjs` -> `pdf.mjs` (core library, ES module)
  - `build/pdf.worker.mjs` -> `pdf.worker.mjs` (PDF parsing worker, ES module)
  - `LICENSE` -> `LICENSE` (Apache License 2.0, applies to both files above)
- Not vendored from the artefact: `build/pdf.sandbox.mjs` (XFA form scripting sandbox, not
  needed for plain PDF viewing), and the whole `web/` directory (upstream's own viewer UI/CSS,
  superseded by this app's own viewer).
- The "legacy" build was chosen over the "default" `pdfjs-6.3.289-dist.zip` because it targets a
  wider range of runtimes; both artefacts ship ES modules only (pdf.js dropped its classic UMD
  bundle in v4). There is no non-module build to fetch instead.
- No network fetch happens at runtime: both files are loaded from this directory as plain static
  assets, and the worker is pointed at the local `pdf.worker.mjs` copy.
- Retrieved 2026-09-04 via the GitHub Releases API/download URLs above (plain `curl`, no auth).
