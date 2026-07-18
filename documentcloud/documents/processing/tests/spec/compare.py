"""
Compare a freshly-processed document directory against a committed golden
(`expected/`) directory.

Two strictness modes serve two different questions:

``exact`` (default) — "is the current pipeline unchanged?"  Used by
test_spec.py for regression testing.  Rules, per file type:

- ``pages/*.txt``, ``{slug}.txt``   exact bytes
- ``{slug}.txt.json``               JSON equality with all ``updated``
                                    timestamps normalized (they are wall
                                    clock times)
- ``pages/*.position.json``         JSON equality with a small float
                                    tolerance on coordinates
- ``pages/*.gif``                   exact bytes; on mismatch the images are
                                    decoded and the pixel difference is
                                    reported to distinguish real rendering
                                    changes from metadata drift
- ``{slug}.pdf``                    semantic comparison (page count, page
                                    dimensions, per-page extracted text).
                                    Byte comparison is skipped: the OCR
                                    grafter writes uuid-named XObjects and
                                    non-reproducible ids
- ``{slug}.index``, ``*.pagesize``  presence only (implementation artifacts,
                                    not part of the output contract; the
                                    index is a gzip whose bytes embed a
                                    timestamp)
- ``metadata.json``                 the merged database fields and the full
                                    API callback sequence (order, methods,
                                    URLs, payloads), with page_spec decoded,
                                    file_hash loosened to presence+shape for
                                    redaction cases, and bucket prefixes
                                    stripped from error messages

``equivalent`` — "does a different implementation produce equivalent final
output?"  For validating a modified or replacement pipeline (different
renderer, OCR engine, or PDF library) against the same goldens:

- text is compared with trailing control characters normalized away (the
  current pipeline's trailing NUL from pdfium and trailing form feed from
  Tesseract are treated as implementation accidents, not contract);
  OCR-produced text must reach a similarity ratio rather than match exactly
- images must have the same dimensions and a small mean pixel difference
  rather than identical bytes
- positions must parse, stay within the 0-1 coordinate range, agree on
  emptiness, and carry approximately the same text
- the PDF must have the same page count, dimensions within tolerance, and
  a similar text layer
- metadata: page_count and status exact; page_spec decoded with a small
  dimension tolerance; file_hash present and well-formed but not compared
  by value; the callback *sequence* is not compared (message choreography
  is not the contract), but error reports must still be sent
- txt.json: page structure and lang exact; the ``ocr`` field is compared
  as OCR'd-or-not rather than by engine name

The equivalence thresholds are a first cut — tune them as real replacement
candidates are evaluated.
"""

# Standard Library
import difflib
import io
import json
import re
from pathlib import Path

POSITION_TOLERANCE = 1e-4

PRESENCE_ONLY_SUFFIXES = (".index", ".pagesize")

# Equivalence-mode thresholds
OCR_TEXT_SIMILARITY = 0.90
POSITION_TEXT_SIMILARITY = 0.80
PDF_TEXT_SIMILARITY = 0.90
IMAGE_MEAN_DELTA = 4.0  # mean absolute per-channel difference, 0-255
DIMENSION_TOLERANCE = 0.5  # PDF points

# Trailing characters the current implementation emits but which are not
# treated as contract in equivalence mode: pdfium terminates extracted text
# with NUL, Tesseract with a form feed
CONTROL_CHARS = "\x00\x0c"

PAGE_FILE = re.compile(r"-p(\d+)\.(txt|position\.json)$")
SHA1_HEX = re.compile(r"^[0-9a-f]{40}$")
# Error messages may embed storage paths whose bucket prefix varies by
# environment; compare from the documents/ segment on
BUCKET_PREFIX = re.compile(r"[^\s']*documents/")


def compare_case(
    expected_dir, actual_dir, ignore_metadata_fields=(), strictness="exact"
):
    """Compare two document directories.  Returns a list of human-readable
    problems; an empty list means the directories match.

    ignore_metadata_fields lists metadata.json database fields excluded from
    comparison — used for file_hash on redaction cases, where the final PDF
    is rewritten with non-reproducible ids so its hash differs run to run.

    strictness is "exact" (regression testing the current pipeline) or
    "equivalent" (validating a replacement implementation); see the module
    docstring."""
    assert strictness in ("exact", "equivalent")
    expected_dir = Path(expected_dir)
    actual_dir = Path(actual_dir)
    context = {
        "strictness": strictness,
        "ignore_fields": ignore_metadata_fields,
        # 0-indexed page numbers the golden marks as OCR'd, for text
        # similarity rules in equivalence mode
        "ocr_pages": _expected_ocr_pages(expected_dir),
    }
    problems = []

    expected_files = _relative_files(expected_dir)
    actual_files = _relative_files(actual_dir)

    for missing in sorted(expected_files - actual_files):
        problems.append(f"missing output file: {missing}")
    for extra in sorted(actual_files - expected_files):
        problems.append(f"unexpected output file: {extra}")

    for name in sorted(expected_files & actual_files):
        problems.extend(
            _compare_file(expected_dir / name, actual_dir / name, name, context)
        )

    return problems


def _relative_files(directory):
    return {
        str(file_path.relative_to(directory))
        for file_path in directory.rglob("*")
        if file_path.is_file()
    }


def _expected_ocr_pages(expected_dir):
    """The set of 0-indexed pages the golden txt.json marks as OCR'd."""
    for json_text_path in Path(expected_dir).glob("*.txt.json"):
        document = json.loads(json_text_path.read_text())
        return {page["page"] for page in document.get("pages", []) if page.get("ocr")}
    return set()


def _page_number(name):
    """0-indexed page number of a per-page file, or None."""
    match = PAGE_FILE.search(name)
    return int(match.group(1)) - 1 if match else None


def _normalize_text(text):
    return text.strip(CONTROL_CHARS + " \t\r\n")


def _similarity(expected_text, actual_text):
    return difflib.SequenceMatcher(
        None, _normalize_text(expected_text), _normalize_text(actual_text)
    ).ratio()


def _compare_file(expected, actual, name, context):
    # pylint: disable=too-many-return-statements
    if name == "metadata.json":
        return _compare_metadata(expected, actual, name, context)
    if name.endswith(PRESENCE_ONLY_SUFFIXES):
        return []  # presence already checked
    if name.endswith(".position.json"):
        return _compare_positions(expected, actual, name, context)
    if name.endswith(".txt.json"):
        return _compare_json_text(expected, actual, name, context)
    if name.endswith(".txt"):
        return _compare_text(expected, actual, name, context)
    if name.endswith(".gif"):
        return _compare_images(expected, actual, name, context)
    if name.endswith(".pdf"):
        return _compare_pdfs(expected, actual, name, context)
    return _compare_bytes(expected, actual, name)


def _compare_bytes(expected, actual, name):
    if expected.read_bytes() != actual.read_bytes():
        return [f"{name}: contents differ"]
    return []


def _compare_text(expected, actual, name, context):
    if context["strictness"] == "exact":
        return _compare_bytes(expected, actual, name)
    expected_text = expected.read_text(encoding="utf-8")
    actual_text = actual.read_text(encoding="utf-8")
    page = _page_number(name)
    # A page is held to the similarity threshold if the golden marks it as
    # OCR'd; the concatenated document text is if any page was OCR'd
    ocr = (
        page in context["ocr_pages"] if page is not None else bool(context["ocr_pages"])
    )
    if ocr:
        ratio = _similarity(expected_text, actual_text)
        if ratio < OCR_TEXT_SIMILARITY:
            return [
                f"{name}: OCR text similarity {ratio:.3f} below "
                f"{OCR_TEXT_SIMILARITY}"
            ]
        return []
    if _normalize_text(expected_text) != _normalize_text(actual_text):
        return [f"{name}: text differs (after trailing-control normalization)"]
    return []


def _compare_metadata(expected, actual, name, context):
    expected_metadata = json.loads(expected.read_text())
    actual_metadata = json.loads(actual.read_text())
    problems = _compare_database(
        expected_metadata["database"],
        actual_metadata["database"],
        name,
        context,
    )
    if context["strictness"] == "exact":
        problems.extend(
            _compare_callbacks(
                expected_metadata.get("callbacks", []),
                actual_metadata.get("callbacks", []),
                name,
                loose_file_hash="file_hash" in context["ignore_fields"],
            )
        )
    else:
        # Message choreography is not the contract for a replacement, but
        # error reports are: the same error endpoints must be hit
        expected_errors = [
            (callback["method"], callback["url"])
            for callback in expected_metadata.get("errors", [])
        ]
        actual_errors = [
            (callback["method"], callback["url"])
            for callback in actual_metadata.get("errors", [])
        ]
        if expected_errors != actual_errors:
            problems.append(
                f"{name}: error reports differ: expected {expected_errors!r}, "
                f"got {actual_errors!r}"
            )
    return problems


def _compare_database(expected_database, actual_database, name, context):
    equivalent = context["strictness"] == "equivalent"
    problems = []
    for field in sorted(set(expected_database) | set(actual_database)):
        if field in context["ignore_fields"]:
            continue
        expected_value = expected_database.get(field)
        actual_value = actual_database.get(field)
        if field == "page_spec":
            # The segment order within a page_spec depends on Redis set
            # iteration order and is not deterministic; compare the decoded
            # per-page dimensions instead
            tolerance = DIMENSION_TOLERANCE if equivalent else 0.0
            if not _page_specs_match(expected_value, actual_value, tolerance):
                problems.append(
                    f"{name}: page_spec decodes differently: "
                    f"expected {expected_value!r}, got {actual_value!r}"
                )
        elif field == "file_hash" and equivalent:
            # A replacement produces different PDF bytes; require a
            # well-formed hash, not the same one
            if not (isinstance(actual_value, str) and SHA1_HEX.match(actual_value)):
                problems.append(
                    f"{name}: file_hash is not a well-formed SHA-1: "
                    f"{actual_value!r}"
                )
        elif expected_value != actual_value:
            problems.append(
                f"{name}: database field {field!r} differs: "
                f"expected {expected_value!r}, got {actual_value!r}"
            )
    return problems


def _normalize_callback(callback, loose_file_hash):
    """Normalize one captured API callback for comparison.

    - page_spec values are decoded (segment order is not deterministic)
    - file_hash values are replaced by a placeholder when loose_file_hash is
      set (redaction rewrites the PDF non-reproducibly), so the sequence
      still asserts that a well-formed hash was sent, just not its value
    - storage bucket prefixes in error messages are stripped
    """
    json_ = dict(callback.get("json", {}))
    if "page_spec" in json_:
        json_["page_spec"] = _decode_page_spec(json_["page_spec"])
    if (
        loose_file_hash
        and isinstance(json_.get("file_hash"), str)
        and SHA1_HEX.match(json_["file_hash"])
    ):
        json_["file_hash"] = "<sha1>"
    if isinstance(json_.get("message"), str):
        json_["message"] = BUCKET_PREFIX.sub("documents/", json_["message"])
    return {
        "method": callback.get("method"),
        "url": callback.get("url"),
        "json": json_,
    }


def _compare_callbacks(expected_callbacks, actual_callbacks, name, loose_file_hash):
    expected_normalized = [
        _normalize_callback(callback, loose_file_hash)
        for callback in expected_callbacks
    ]
    actual_normalized = [
        _normalize_callback(callback, loose_file_hash) for callback in actual_callbacks
    ]
    if expected_normalized == actual_normalized:
        return []
    problems = []
    if len(expected_normalized) != len(actual_normalized):
        problems.append(
            f"{name}: callback count differs: expected "
            f"{len(expected_normalized)}, got {len(actual_normalized)}"
        )
    for index, (expected_callback, actual_callback) in enumerate(
        zip(expected_normalized, actual_normalized)
    ):
        if expected_callback != actual_callback:
            problems.append(
                f"{name}: callback {index} differs: "
                f"expected {expected_callback!r}, got {actual_callback!r}"
            )
    return problems or [f"{name}: callback sequences differ"]


def _decode_page_spec(page_spec):
    """Decode a crunched page_spec string into a page number to dimension
    mapping (e.g. "612.00x792.00:0-1" -> {0: "612.00x792.00", 1: ...})."""
    if not isinstance(page_spec, str):
        return page_spec
    pages = {}
    for segment in page_spec.split(";"):
        dimension, _, page_ranges = segment.partition(":")
        for page_range in page_ranges.split(","):
            start, _, end = page_range.partition("-")
            for page in range(int(start), int(end or start) + 1):
                pages[page] = dimension
    return pages


def _page_specs_match(expected_spec, actual_spec, tolerance):
    expected_pages = _decode_page_spec(expected_spec)
    actual_pages = _decode_page_spec(actual_spec)
    if not isinstance(expected_pages, dict) or not isinstance(actual_pages, dict):
        return expected_pages == actual_pages
    if set(expected_pages) != set(actual_pages):
        return False
    for page, expected_dimension in expected_pages.items():
        actual_dimension = actual_pages[page]
        if expected_dimension == actual_dimension:
            continue
        if tolerance <= 0:
            return False
        try:
            expected_w, expected_h = map(float, expected_dimension.split("x"))
            actual_w, actual_h = map(float, actual_dimension.split("x"))
        except ValueError:
            return False
        if (
            abs(expected_w - actual_w) > tolerance
            or abs(expected_h - actual_h) > tolerance
        ):
            return False
    return True


def _normalize_updated(document):
    document = dict(document)
    document["updated"] = 0
    document["pages"] = [{**page, "updated": 0} for page in document.get("pages", [])]
    return document


def _normalize_page_equivalent(page):
    """In equivalence mode a page's ocr field is compared as OCR'd-or-not
    (a replacement may use a different engine label) and its contents are
    compared separately with text rules."""
    page = dict(page)
    page["ocr"] = bool(page.get("ocr"))
    page.pop("contents", None)
    return page


def _compare_json_text(expected, actual, name, context):
    # pylint: disable=too-many-locals
    equivalent = context["strictness"] == "equivalent"
    expected_json = _normalize_updated(json.loads(expected.read_text()))
    actual_json = _normalize_updated(json.loads(actual.read_text()))
    problems = []
    expected_pages = expected_json.get("pages", [])
    actual_pages = actual_json.get("pages", [])
    if len(expected_pages) != len(actual_pages):
        return [
            f"{name}: page count differs: expected {len(expected_pages)}, "
            f"got {len(actual_pages)}"
        ]
    for index, (expected_page, actual_page) in enumerate(
        zip(expected_pages, actual_pages)
    ):
        if equivalent:
            expected_contents = expected_page.get("contents", "")
            actual_contents = actual_page.get("contents", "")
            if expected_page.get("ocr"):
                ratio = _similarity(expected_contents, actual_contents)
                if ratio < OCR_TEXT_SIMILARITY:
                    problems.append(
                        f"{name}: page {index} OCR text similarity "
                        f"{ratio:.3f} below {OCR_TEXT_SIMILARITY}"
                    )
            elif _normalize_text(expected_contents) != _normalize_text(actual_contents):
                problems.append(f"{name}: page {index} contents differ")
            expected_page = _normalize_page_equivalent(expected_page)
            actual_page = _normalize_page_equivalent(actual_page)
        if expected_page != actual_page:
            for key in sorted(set(expected_page) | set(actual_page)):
                if expected_page.get(key) != actual_page.get(key):
                    problems.append(
                        f"{name}: page {index} field {key!r} differs: "
                        f"expected {expected_page.get(key)!r}, "
                        f"got {actual_page.get(key)!r}"
                    )
    top_expected = {k: v for k, v in expected_json.items() if k != "pages"}
    top_actual = {k: v for k, v in actual_json.items() if k != "pages"}
    if top_expected != top_actual:
        problems.append(
            f"{name}: top-level fields differ: expected {top_expected!r}, "
            f"got {top_actual!r}"
        )
    return problems


def _compare_positions(expected, actual, name, context):
    expected_words = json.loads(expected.read_text())
    actual_words = json.loads(actual.read_text())
    if context["strictness"] == "equivalent":
        return _compare_positions_equivalent(expected_words, actual_words, name)
    if len(expected_words) != len(actual_words):
        return [
            f"{name}: word count differs: expected {len(expected_words)}, "
            f"got {len(actual_words)}"
        ]
    problems = []
    for index, (expected_word, actual_word) in enumerate(
        zip(expected_words, actual_words)
    ):
        for key in sorted(set(expected_word) | set(actual_word)):
            expected_value = expected_word.get(key)
            actual_value = actual_word.get(key)
            if isinstance(expected_value, float) and isinstance(
                actual_value, (int, float)
            ):
                if abs(expected_value - actual_value) > POSITION_TOLERANCE:
                    problems.append(
                        f"{name}: word {index} {key!r} differs beyond "
                        f"tolerance: expected {expected_value!r}, "
                        f"got {actual_value!r}"
                    )
            elif expected_value != actual_value:
                problems.append(
                    f"{name}: word {index} {key!r} differs: "
                    f"expected {expected_value!r}, got {actual_value!r}"
                )
    return problems


def _compare_positions_equivalent(expected_words, actual_words, name):
    """A replacement extractor may segment words differently; require valid
    structure, in-range coordinates, agreement on emptiness, and
    approximately the same text."""
    problems = []
    if bool(expected_words) != bool(actual_words):
        return [
            f"{name}: emptiness differs: expected {len(expected_words)} "
            f"words, got {len(actual_words)}"
        ]
    for index, word in enumerate(actual_words):
        for key in ("x1", "x2", "y1", "y2"):
            value = word.get(key)
            if not isinstance(value, (int, float)) or not 0 <= value <= 1:
                problems.append(f"{name}: word {index} {key!r} out of range: {value!r}")
        if not isinstance(word.get("text"), str):
            problems.append(f"{name}: word {index} has no text")
    expected_text = " ".join(word.get("text", "") for word in expected_words)
    actual_text = " ".join(word.get("text", "") for word in actual_words)
    ratio = _similarity(expected_text, actual_text)
    if expected_words and ratio < POSITION_TEXT_SIMILARITY:
        problems.append(
            f"{name}: position text similarity {ratio:.3f} below "
            f"{POSITION_TEXT_SIMILARITY}"
        )
    return problems


def _compare_images(expected, actual, name, context):
    # pylint: disable=too-many-locals, too-many-return-statements
    expected_bytes = expected.read_bytes()
    actual_bytes = actual.read_bytes()
    if expected_bytes == actual_bytes:
        return []
    equivalent = context["strictness"] == "equivalent"

    # Third Party
    from PIL import Image, ImageChops, ImageStat

    expected_image = Image.open(io.BytesIO(expected_bytes)).convert("RGB")
    actual_image = Image.open(io.BytesIO(actual_bytes)).convert("RGB")
    if expected_image.size != actual_image.size:
        return [
            f"{name}: image size differs: expected {expected_image.size}, "
            f"got {actual_image.size}"
        ]
    difference = ImageChops.difference(expected_image, actual_image)
    bounding_box = difference.getbbox()
    if bounding_box is None:
        if equivalent:
            return []
        return [f"{name}: bytes differ but pixels are identical"]
    mean_delta = max(ImageStat.Stat(difference).mean)
    if equivalent:
        if mean_delta <= IMAGE_MEAN_DELTA:
            return []
        return [
            f"{name}: mean pixel delta {mean_delta:.2f} above " f"{IMAGE_MEAN_DELTA}"
        ]
    max_channel_difference = max(band.getextrema()[1] for band in difference.split())
    return [
        f"{name}: pixels differ in region {bounding_box} "
        f"(max channel delta {max_channel_difference}, mean {mean_delta:.2f})"
    ]


def _pdf_summary(pdf_path):
    # Third Party
    import pymupdf

    summary = []
    with pymupdf.open(str(pdf_path)) as pdf:
        for page in pdf:
            summary.append(
                {
                    "width": round(page.rect.width, 2),
                    "height": round(page.rect.height, 2),
                    "text": page.get_text(),
                }
            )
    return summary


def _compare_pdfs(expected, actual, name, context):
    equivalent = context["strictness"] == "equivalent"
    try:
        expected_summary = _pdf_summary(expected)
        actual_summary = _pdf_summary(actual)
    except Exception:  # pylint: disable=broad-except
        # Unparseable PDF (e.g. the corrupt-input error case): fall back to
        # comparing the raw bytes
        return _compare_bytes(expected, actual, name)
    problems = []
    if len(expected_summary) != len(actual_summary):
        return [
            f"{name}: page count differs: expected {len(expected_summary)}, "
            f"got {len(actual_summary)}"
        ]
    for index, (expected_page, actual_page) in enumerate(
        zip(expected_summary, actual_summary)
    ):
        for key in ("width", "height"):
            delta = abs(expected_page[key] - actual_page[key])
            if delta > (DIMENSION_TOLERANCE if equivalent else 0):
                problems.append(
                    f"{name}: page {index + 1} {key} differs: "
                    f"expected {expected_page[key]}, got {actual_page[key]}"
                )
        if equivalent:
            ratio = _similarity(expected_page["text"], actual_page["text"])
            if ratio < PDF_TEXT_SIMILARITY:
                problems.append(
                    f"{name}: page {index + 1} text layer similarity "
                    f"{ratio:.3f} below {PDF_TEXT_SIMILARITY}"
                )
        elif expected_page["text"] != actual_page["text"]:
            problems.append(f"{name}: page {index + 1} text layer differs")
    return problems
