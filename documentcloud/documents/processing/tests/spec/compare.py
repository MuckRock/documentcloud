"""
Compare a freshly-processed document directory against a committed golden
(`expected/`) directory.

Comparison rules, per file type:

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
- ``metadata.json``                 the database-facing fields must match
                                    exactly: page_count, page_spec,
                                    file_hash, status
"""

# Standard Library
import io
import json
from pathlib import Path

POSITION_TOLERANCE = 1e-4

PRESENCE_ONLY_SUFFIXES = (".index", ".pagesize")


def compare_case(expected_dir, actual_dir, ignore_metadata_fields=()):
    """Compare two document directories.  Returns a list of human-readable
    problems; an empty list means the directories match.

    ignore_metadata_fields lists metadata.json database fields excluded from
    comparison — used for file_hash on redaction cases, where the final PDF
    is rewritten with non-reproducible ids so its hash differs run to run."""
    expected_dir = Path(expected_dir)
    actual_dir = Path(actual_dir)
    problems = []

    expected_files = _relative_files(expected_dir)
    actual_files = _relative_files(actual_dir)

    for missing in sorted(expected_files - actual_files):
        problems.append(f"missing output file: {missing}")
    for extra in sorted(actual_files - expected_files):
        problems.append(f"unexpected output file: {extra}")

    for name in sorted(expected_files & actual_files):
        problems.extend(
            _compare_file(
                expected_dir / name,
                actual_dir / name,
                name,
                ignore_metadata_fields,
            )
        )

    return problems


def _relative_files(directory):
    return {
        str(file_path.relative_to(directory))
        for file_path in directory.rglob("*")
        if file_path.is_file()
    }


def _compare_file(expected, actual, name, ignore_metadata_fields=()):
    # pylint: disable=too-many-return-statements
    if name == "metadata.json":
        return _compare_metadata(expected, actual, name, ignore_metadata_fields)
    if name.endswith(PRESENCE_ONLY_SUFFIXES):
        return []  # presence already checked
    if name.endswith(".position.json"):
        return _compare_positions(expected, actual, name)
    if name.endswith(".txt.json"):
        return _compare_json_text(expected, actual, name)
    if name.endswith(".txt"):
        return _compare_bytes(expected, actual, name)
    if name.endswith(".gif"):
        return _compare_images(expected, actual, name)
    if name.endswith(".pdf"):
        return _compare_pdfs(expected, actual, name)
    return _compare_bytes(expected, actual, name)


def _compare_bytes(expected, actual, name):
    if expected.read_bytes() != actual.read_bytes():
        return [f"{name}: contents differ"]
    return []


def _compare_metadata(expected, actual, name, ignore_fields=()):
    problems = []
    expected_database = json.loads(expected.read_text())["database"]
    actual_database = json.loads(actual.read_text())["database"]
    for field in sorted(set(expected_database) | set(actual_database)):
        if field in ignore_fields:
            continue
        expected_value = expected_database.get(field)
        actual_value = actual_database.get(field)
        if field == "page_spec":
            # The segment order within a page_spec depends on Redis set
            # iteration order and is not deterministic; compare the decoded
            # per-page dimensions instead
            if _decode_page_spec(expected_value) != _decode_page_spec(actual_value):
                problems.append(
                    f"{name}: page_spec decodes differently: "
                    f"expected {expected_value!r}, got {actual_value!r}"
                )
        elif expected_value != actual_value:
            problems.append(
                f"{name}: database field {field!r} differs: "
                f"expected {expected_value!r}, got {actual_value!r}"
            )
    return problems


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


def _normalize_updated(document):
    document = dict(document)
    document["updated"] = 0
    document["pages"] = [{**page, "updated": 0} for page in document.get("pages", [])]
    return document


def _compare_json_text(expected, actual, name):
    expected_json = _normalize_updated(json.loads(expected.read_text()))
    actual_json = _normalize_updated(json.loads(actual.read_text()))
    if expected_json != actual_json:
        problems = []
        expected_pages = expected_json.get("pages", [])
        actual_pages = actual_json.get("pages", [])
        if len(expected_pages) != len(actual_pages):
            problems.append(
                f"{name}: page count differs: expected {len(expected_pages)}, "
                f"got {len(actual_pages)}"
            )
        for index, (expected_page, actual_page) in enumerate(
            zip(expected_pages, actual_pages)
        ):
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
        return problems or [f"{name}: contents differ"]
    return []


def _compare_positions(expected, actual, name):
    expected_words = json.loads(expected.read_text())
    actual_words = json.loads(actual.read_text())
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


def _compare_images(expected, actual, name):
    expected_bytes = expected.read_bytes()
    actual_bytes = actual.read_bytes()
    if expected_bytes == actual_bytes:
        return []

    # Third Party
    from PIL import Image, ImageChops

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
        return [f"{name}: bytes differ but pixels are identical"]
    max_channel_difference = max(band.getextrema()[1] for band in difference.split())
    return [
        f"{name}: pixels differ in region {bounding_box} "
        f"(max channel delta {max_channel_difference})"
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


def _compare_pdfs(expected, actual, name):
    expected_summary = _pdf_summary(expected)
    actual_summary = _pdf_summary(actual)
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
            if expected_page[key] != actual_page[key]:
                problems.append(
                    f"{name}: page {index + 1} {key} differs: "
                    f"expected {expected_page[key]}, got {actual_page[key]}"
                )
        if expected_page["text"] != actual_page["text"]:
            problems.append(f"{name}: page {index + 1} text layer differs")
    return problems
