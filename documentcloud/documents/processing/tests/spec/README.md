# Processing Pipeline Test Spec

Golden-output tests for the document processing pipeline. For each test
document in `documents/`, the `expected/` directory contains **every file the
current pipeline produces** for that document, plus the database-facing
metadata sent back to the API. The goal is to be able to change processing
code and validate that the outputs (or exactly the outputs you intended to
change) stay the same.

This builds on the output-contract spec in
[MuckRock/research `processing-pipeline-spec`](https://github.com/MuckRock/research/tree/main/processing-pipeline-spec),
which documents *what* the pipeline must produce. This directory makes that
contract executable against the real implementation.

## Layout

```
spec/
├── harness.py          # runs the real pipeline in-process (no mocks)
├── compare.py          # comparison / normalization rules
├── generate.py         # regenerates the golden outputs
├── test_spec.py        # pytest: fresh run must match expected/
├── make_corpus.py      # builds the input PDFs (deterministic)
└── documents/
    └── <case>/
        ├── case.json   # doc_id, slug, processing settings, redactions
        ├── input/      # the "uploaded" document
        └── expected/   # everything the pipeline produced
            ├── <slug>.pdf         # processed PDF (OCR text grafted in)
            ├── <slug>.txt         # concatenated text, pages joined by \n\n
            ├── <slug>.txt.json    # per-page text + OCR metadata
            ├── <slug>.index       # I/O cache (implementation artifact)
            ├── pages/
            │   ├── <slug>-p<N>-{xlarge,large,normal,small,thumbnail}.gif
            │   ├── <slug>-p<N>.txt
            │   └── <slug>-p<N>.position.json
            └── metadata.json      # captured API callbacks: page_count,
                                   # page_spec, file_hash, status
```

`metadata.json` is not a pipeline storage file — it records what the pipeline
PATCHed back to the API (the `database` key is the merged final state, and
`callbacks` is the raw sequence of requests).

## How the harness works

`harness.PipelineRunner` runs the actual serverless functions
(`info_and_image/main.py`, `ocr/main.py`) with:

- the `local` storage environment writing under a temporary `MEDIA_ROOT`
- a real Redis (`REDIS_PROCESSING_URL`, defaults to `localhost:6379` — the
  same requirement the existing pipeline tests have in CI)
- pubsub topics dispatched through an in-process FIFO queue, so each function
  runs to completion before the next starts (in production every message runs
  in its own Lambda; pdfium cannot be nested inside one process)
- API callbacks (`serverless.utils.request`) captured instead of sent

Nothing inside the pipeline is mocked: pdfium rendering and text extraction,
Tesseract OCR, PDF grafting, pdfplumber text positions, and page_spec
crunching all run for real.

## Test corpus

| Case | Pages | What it validates |
| --- | --- | --- |
| `text-1page` | 1 | Baseline: embedded text, no OCR, full output file set |
| `text-3page` | 3 | All pages get all artifacts; concatenation order |
| `scan-2page` | 2 | Image-only pages: OCR text, grafting, OCR positions |
| `mixed-2page` | 2 | Per-page routing: page 1 `ocr: null`, page 2 `ocr: "tess4"` |
| `force-ocr-1page` | 1 | `force_ocr` overrides embedded text (`ocr: "tess4_force"`) |
| `mixed-sizes-2page` | 2 | Differing page dimensions; page_spec encoding |
| `blank-1page` | 1 | Blank page is OCR'd; produces `"\f"` text and `[]` positions |
| `redact-2page` | 2 | Redaction path: only the dirty page is reprocessed; page_spec is not resent |

Inputs are built deterministically by `make_corpus.py` and committed, so the
goldens always correspond to known input bytes.

## Running the validation

```bash
pytest documentcloud/documents/processing/tests/spec/test_spec.py
```

This runs in CI alongside the other tests (it needs the Redis service the
existing pipeline tests already use). Cases that need OCR are skipped unless
the OCR runtime is available (see below); the embedded-text cases always run.

To check outside of pytest:

```bash
python documentcloud/documents/processing/tests/spec/generate.py --check
```

## Regenerating the goldens

After an *intentional* change to pipeline behavior:

```bash
python documentcloud/documents/processing/tests/spec/generate.py [case ...]
```

then review the diff — it is a precise inventory of what your change did to
the pipeline's output — and commit it.

### OCR requirements

The OCR cases run the bundled Tesseract, which is stored in Git LFS:

```bash
git lfs pull --include "documentcloud/documents/processing/ocr/tesseract/*"
```

OCR output is only comparable when produced with the same language data, so
the harness pins `eng.traineddata` by content hash
(`tessdata_fast` 4.1.0; `generate.py` downloads it into `.cache/` on first
use). If you want goldens that match production OCR exactly, place the
production `eng.traineddata` (from the `ocr-languages` storage folder) in
`.cache/` instead and regenerate — but note the committed goldens must then
be produced with that same file.

## Comparison rules

Some pipeline output is intentionally or unavoidably non-reproducible, so
`compare.py` normalizes:

| Output | Rule |
| --- | --- |
| `*.txt` (full and per-page) | exact bytes |
| `*.txt.json` | JSON equality; `updated` timestamps ignored (wall clock) |
| `*.position.json` | JSON equality; coordinate floats within `1e-4` |
| `*.gif` | exact bytes; on mismatch, pixels are diffed and reported |
| `*.pdf` | semantic: page count, page dimensions, per-page text layer. Bytes are not compared — the OCR grafter writes uuid-named XObjects and pikepdf regenerates the document ID |
| `*.index` | presence only (gzip bytes embed a timestamp; not part of the contract) |
| `metadata.json` | `page_count` and `status` exact; `page_spec` compared decoded (segment order follows Redis set iteration and is not deterministic); `file_hash` exact, except for redaction cases where the final PDF is rewritten non-reproducibly |

Behaviors of the current pipeline that the goldens capture and that any
reimplementation would need to match (or knowingly change):

- Text extracted by pdfium ends with a trailing NUL (`\x00`) character
- Text produced by Tesseract ends with a form feed (`\f`); a blank page
  yields `"\f"`, not the empty string
- Pages in `<slug>.txt` are joined with `\n\n`
- `ocr` values in `txt.json`: `null` (embedded text), `"tess4"`,
  `"tess4_force"` (when `force_ocr` is set)
- The `updated` timestamps are milliseconds; each page carries its own
- `file_hash` is the SHA-1 of the PDF as hashed during page-cache processing
  (before OCR grafting rewrites it)
- Redaction re-sends `file_hash` and `status` but not `page_spec`

## Not covered yet

- **Textract OCR** (`ocr_engine: "textract"`) — requires AWS and an AI-credit
  API; the golden harness only runs Tesseract
- **Non-PDF uploads** — document conversion needs the LibreOffice bundle
  (`document_conversion/libreoffice/lo.tar.gz`, a large LFS object)
- **Page modifications** (reorder / rotate / insert) — the modify path needs
  `storage.async_download`, which the local storage backend does not implement
- **Bulk import**, **set_page_text**, revision control copies
- **Non-English OCR** — needs additional pinned traineddata files
- **Large documents** (image batching across multiple messages) — would bloat
  the repository; `IMAGE_BATCH` behavior is still exercised, just with small
  page counts
