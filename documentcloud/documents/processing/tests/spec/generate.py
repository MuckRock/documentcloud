#!/usr/bin/env python
"""
(Re)generate the golden outputs for the processing pipeline test spec.

For every test case under `documents/`, this runs the current pipeline
against the case's input document and snapshots everything it produced —
the storage files and the database-facing metadata — into the case's
`expected/` directory.

Run this after intentionally changing pipeline behavior, review the diff,
and commit the result.  `test_spec.py` then validates that the pipeline
still produces these outputs.

Requirements:
    - a running Redis (REDIS_PROCESSING_URL, defaults to localhost:6379)
    - for OCR cases: the Git LFS Tesseract libraries
      (git lfs pull --include "documentcloud/documents/processing/ocr/tesseract/*")
      and the pinned eng.traineddata (downloaded automatically on first run)

Usage:
    python generate.py [case ...]        # default: all cases
    python generate.py --check [case ...]  # regenerate into a scratch dir and
                                            # compare against expected/ instead
                                            # of overwriting it
"""

# Standard Library
import argparse
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parents[5]
sys.path.insert(0, str(REPO_ROOT))

# DocumentCloud
from documentcloud.documents.processing.tests.spec import compare, harness


def snapshot(runner, case, metadata, destination):
    """Copy a processed document directory plus its captured metadata into
    the destination directory."""
    # Standard Library
    import json

    destination = Path(destination)
    shutil.rmtree(destination, ignore_errors=True)
    shutil.copytree(runner.doc_directory(case), destination)
    with open(destination / "metadata.json", "w", encoding="utf-8") as meta_file:
        json.dump(metadata, meta_file, indent=2, sort_keys=True)
        meta_file.write("\n")


def main(argv):
    # pylint: disable=too-many-locals
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="*", help="case names (default: all)")
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare a fresh run against expected/ instead of overwriting",
    )
    args = parser.parse_args(argv)

    harness.ensure_environment()

    cases = harness.all_cases()
    if args.cases:
        cases = [case for case in cases if case["name"] in args.cases]
        missing = set(args.cases) - {case["name"] for case in cases}
        if missing:
            parser.error(f"unknown cases: {', '.join(sorted(missing))}")

    ocr_ready = harness.ocr_ready(download=True)
    skipped = [case["name"] for case in cases if case["needs_ocr"] and not ocr_ready]
    cases = [case for case in cases if not case["needs_ocr"] or ocr_ready]
    if skipped:
        print(
            "OCR unavailable (git lfs pull the tesseract libraries and ensure "
            f"the traineddata is present); skipping: {', '.join(skipped)}"
        )

    failures = []
    media_root = Path(tempfile.mkdtemp(prefix="dc-processing-spec-"))
    try:
        with harness.PipelineRunner(media_root, use_ocr=ocr_ready) as runner:
            for case in cases:
                print(f"processing {case['name']} ...", flush=True)
                metadata = runner.run_case(case)
                if metadata["errors"]:
                    failures.append(
                        f"{case['name']}: pipeline reported errors: "
                        f"{metadata['errors']}"
                    )
                    continue
                if args.check:
                    scratch = media_root / "check" / case["name"]
                    snapshot(runner, case, metadata, scratch)
                    problems = compare.compare_case(
                        case["dir"] / "expected",
                        scratch,
                        ignore_metadata_fields=(
                            ("file_hash",) if case.get("redactions") else ()
                        ),
                    )
                    for problem in problems:
                        failures.append(f"{case['name']}: {problem}")
                    status = "ok" if not problems else f"{len(problems)} problem(s)"
                    print(f"  checked against expected/: {status}")
                else:
                    snapshot(runner, case, metadata, case["dir"] / "expected")
                    print(f"  wrote {case['dir'] / 'expected'}")
    finally:
        shutil.rmtree(media_root, ignore_errors=True)

    if failures:
        print()
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
