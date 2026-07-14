"""
Validate the processing pipeline against the committed golden outputs.

For every case under `documents/` that has an `expected/` directory, run the
real pipeline on the case's input document and compare everything it
produces — storage files and database-facing metadata — against the golden
copies.  See README.md for the comparison rules and how to regenerate the
goldens after an intentional behavior change (`python generate.py`).

Requires a reachable Redis (as the pipeline tests in CI already do).  Cases
that need OCR are skipped unless the Git LFS Tesseract libraries and the
pinned eng.traineddata are present.
"""

# Standard Library
import json
import shutil
import tempfile
from pathlib import Path

# Third Party
import pytest

# DocumentCloud
from documentcloud.documents.processing.tests.spec import compare, harness

# Pytest fixtures are injected by parameter name
# pylint: disable=redefined-outer-name


CASES = [case for case in harness.all_cases() if (case["dir"] / "expected").exists()]


def _case_id(case):
    return case["name"]


@pytest.fixture(scope="module")
def ocr_ready():
    # Downloads the hash-pinned eng.traineddata on first use (a few MB);
    # once cached under spec/.cache/ no network is needed
    return harness.ocr_ready(download=True)


@pytest.mark.slow
@pytest.mark.parametrize("case", CASES, ids=_case_id)
def test_pipeline_output_contract(case, ocr_ready):
    if case["needs_ocr"] and not ocr_ready:
        pytest.skip(
            "OCR unavailable: run git lfs pull --include "
            '"documentcloud/documents/processing/ocr/tesseract/*" and '
            "provide eng.traineddata (see spec/README.md)"
        )

    media_root = Path(tempfile.mkdtemp(prefix="dc-processing-spec-"))
    try:
        with harness.PipelineRunner(media_root, use_ocr=ocr_ready) as runner:
            metadata = runner.run_case(case)
            assert not metadata[
                "errors"
            ], f"pipeline reported errors: {metadata['errors']}"

            actual_dir = media_root / "actual"
            shutil.copytree(runner.doc_directory(case), actual_dir)
            with open(actual_dir / "metadata.json", "w", encoding="utf-8") as meta_file:
                json.dump(metadata, meta_file)

        problems = compare.compare_case(
            case["dir"] / "expected",
            actual_dir,
            ignore_metadata_fields=(("file_hash",) if case.get("redactions") else ()),
        )
        assert not problems, "\n".join(
            [f"{case['name']} does not match its golden outputs:"] + problems
        )
    finally:
        shutil.rmtree(media_root, ignore_errors=True)
