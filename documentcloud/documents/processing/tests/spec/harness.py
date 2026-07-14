"""
Run the real processing pipeline in-process against local file storage.

This drives the actual serverless functions (info_and_image, ocr) with:

- the `local` environment (files written under MEDIA_ROOT on disk)
- a real Redis instance (`REDIS_PROCESSING_URL`, defaults to localhost:6379)
- pubsub topics wired to an in-process message queue: each function runs to
  completion before the next message is dispatched, mirroring production
  where every message runs in its own Lambda (pdfium cannot be nested
  within one process)
- API callbacks captured instead of sent, so the database-facing side of the
  output contract (page_count, page_spec, file_hash, status) is recorded

Nothing in the pipeline itself is mocked: pdfium rendering, text extraction,
Tesseract OCR, grafting, and text position extraction all run for real.

OCR requirements: the bundled Tesseract shared libraries are stored in Git
LFS (`git lfs pull --include "documentcloud/documents/processing/ocr/tesseract/*"`)
and an `eng.traineddata` must be available (see `fetch_traineddata`).
"""

# Standard Library
import ctypes
import hashlib
import json
import os
import shutil
import urllib.request
from collections import deque
from pathlib import Path

SPEC_DIR = Path(__file__).parent
PROCESSING_DIR = SPEC_DIR.parent.parent
CACHE_DIR = SPEC_DIR / ".cache"
DOCUMENTS_DIR = SPEC_DIR / "documents"

TESSERACT_DIR = PROCESSING_DIR / "ocr" / "tesseract"
# Dependency order matters: each library must be loadable when the next one
# needs it (in production, Lambda's LD_LIBRARY_PATH handles this)
TESSERACT_LIBS = [
    "libjbig.so.0",
    "libpng16.so.16.37.0",
    "libjpeg.so.8.2.2",
    "libwebp.so.6.0.2",
    "libtiff.so.5.5.0",
    "liblept.so.5",
]

# The OCR language data used to generate the golden outputs.  OCR output is
# only comparable when produced with the same traineddata, so the file is
# pinned by content hash.  Production language packs live in the
# `ocr-languages` storage folder; if you want goldens that match production
# OCR exactly, drop the production eng.traineddata into .cache/ instead.
TRAINEDDATA_URL = (
    "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/"
    "eng.traineddata"
)
TRAINEDDATA_SHA256 = "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"

DEFAULT_ENV = {
    "ENVIRONMENT": "local",
    "DOCUMENT_BUCKET": "spec-bucket",
    "API_CALLBACK": "http://api.processing-spec.invalid/api/",
    "PROCESSING_TOKEN": "processing-spec-token",
    "REDIS_PROCESSING_URL": "redis://localhost:6379",
    "REDIS_PROCESSING_PASSWORD": "",
    "USE_TIMEOUT": "false",
    "TIMEOUTS": "15,30,60,120",
    # Required by the local httpsub mock; never actually called by the runner
    "DOC_PROCESSING_URL": "mock://process",
    "PROGRESS_URL": "mock://progress",
    "IMPORT_URL": "mock://import",
    "SIDEKICK_PROCESSING_URL": "mock://sidekick",
}


def ensure_environment():
    """Set the environment variables and Django settings the pipeline modules
    need at import time.  Values already present (e.g. in CI or a dev shell)
    are left untouched."""
    for key, value in DEFAULT_ENV.items():
        os.environ.setdefault(key, value)

    # Django
    from django.conf import settings

    if not settings.configured:
        settings.configure(MEDIA_ROOT="")


def load_case(case_dir):
    """Load a test case definition from its directory."""
    case_dir = Path(case_dir)
    with open(case_dir / "case.json", encoding="utf-8") as case_file:
        case = json.load(case_file)
    case["dir"] = case_dir
    case["name"] = case_dir.name
    case["input"] = case_dir / "input" / f"{case['slug']}.pdf"
    return case


def all_cases():
    """All test case definitions, sorted by name."""
    return [
        load_case(case_dir)
        for case_dir in sorted(DOCUMENTS_DIR.iterdir())
        if (case_dir / "case.json").exists()
    ]


def _is_lfs_pointer(file_path):
    try:
        with open(file_path, "rb") as pointer_file:
            return pointer_file.read(24).startswith(b"version https://git-lfs")
    except OSError:
        return True


def ocr_libraries_available():
    """Whether the bundled Tesseract shared libraries are real files (they
    are stored in Git LFS and may be un-pulled pointers)."""
    return all(
        not _is_lfs_pointer(TESSERACT_DIR / lib)
        for lib in TESSERACT_LIBS + ["libtesseract.so.5"]
    )


def preload_tesseract_libraries():
    """Load libtesseract's dependencies into the process so ctypes can
    resolve them (Lambda does this via LD_LIBRARY_PATH)."""
    for lib in TESSERACT_LIBS:
        ctypes.CDLL(str(TESSERACT_DIR / lib), mode=ctypes.RTLD_GLOBAL)


def traineddata_path():
    """Where the pinned eng.traineddata lives (override dir with
    DC_SPEC_TESSDATA_DIR)."""
    data_dir = Path(os.environ.get("DC_SPEC_TESSDATA_DIR", CACHE_DIR))
    return data_dir / "eng.traineddata"


def fetch_traineddata():
    """Download the pinned eng.traineddata if it is not cached yet.
    Returns its path, or None if it cannot be obtained."""
    data_path = traineddata_path()
    if data_path.exists():
        return data_path
    data_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(TRAINEDDATA_URL, timeout=120) as response:
            contents = response.read()
    except OSError:
        return None
    if hashlib.sha256(contents).hexdigest() != TRAINEDDATA_SHA256:
        raise RuntimeError(
            f"Downloaded traineddata does not match pinned hash "
            f"{TRAINEDDATA_SHA256}"
        )
    data_path.write_bytes(contents)
    return data_path


def ocr_ready(download=False):
    """Whether OCR-dependent cases can run in this checkout."""
    if not ocr_libraries_available():
        return False
    if traineddata_path().exists():
        return True
    return download and fetch_traineddata() is not None


class FakeResponse:
    status_code = 200
    text = ""


class PipelineRunner:
    """Context manager that wires the pipeline up against a MEDIA_ROOT
    directory and runs test cases through it."""

    # pylint: disable=too-many-instance-attributes

    def __init__(self, media_root, use_ocr=True):
        ensure_environment()
        self.media_root = Path(media_root)
        self.use_ocr = use_ocr
        self.callbacks = []
        self._overrides = []

    def __enter__(self):
        # Imports deferred: pipeline modules read env vars at import time
        # Django
        from django.test.utils import override_settings

        # DocumentCloud
        from documentcloud.common.environment import publisher
        from documentcloud.common.serverless import error_handling, utils
        from documentcloud.documents.processing.info_and_image import main as ii_main
        from documentcloud.documents.processing.ocr import main as ocr_main

        self.publisher = publisher
        self.utils = utils
        self.ii_main = ii_main
        self.ocr_main = ocr_main

        self.media_root.mkdir(parents=True, exist_ok=True)
        self._settings_override = override_settings(MEDIA_ROOT=str(self.media_root))
        self._settings_override.enable()

        # Capture API callbacks instead of performing HTTP requests
        self._original_request = utils.request
        utils.request = self._record_callback

        # Never use pebble subprocesses: the queue and the callback recorder
        # live in this process
        self._original_use_timeout = error_handling.USE_TIMEOUT
        error_handling.USE_TIMEOUT = False
        self._error_handling = error_handling

        # Dispatch every topic through the in-process message queue
        self.queue = deque()
        self._original_tasks = dict(publisher.tasks)
        for topic, function in [
            (ii_main.PDF_PROCESS_TOPIC, ii_main.process_pdf),
            (ii_main.PAGE_CACHE_TOPIC, ii_main.process_page_cache),
            (ii_main.IMAGE_EXTRACT_TOPIC, ii_main.extract_image),
            (ii_main.OCR_TOPIC, ocr_main.run_tesseract),
            (ii_main.ASSEMBLE_TEXT_TOPIC, ii_main.assemble_page_text),
            (ii_main.TEXT_POSITION_EXTRACT_TOPIC, ii_main.extract_text_position),
            (ii_main.REDACT_TOPIC, ii_main.redact_doc),
        ]:
            publisher.register_internal_callback(topic, self._enqueue(function))

        if self.use_ocr:
            preload_tesseract_libraries()
            self._stage_ocr_data()

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.publisher.tasks = self._original_tasks
        self.utils.request = self._original_request
        self._error_handling.USE_TIMEOUT = self._original_use_timeout
        self._settings_override.disable()

    def _record_callback(self, _redis, method, url, json_):
        self.callbacks.append({"method": method, "url": url, "json": json_})
        return FakeResponse()

    def _enqueue(self, function):
        def callback(data):
            self.queue.append((function, data))

        return callback

    def _drain(self):
        while self.queue:
            function, data = self.queue.popleft()
            function(data)

    def _stage_ocr_data(self):
        """Place the OCR language data where the pipeline downloads it from
        (the `ocr-languages` folder of local storage)."""
        languages_dir = self.media_root / self.ocr_main.OCR_DATA_DIRECTORY
        languages_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(TESSERACT_DIR / "tessdata" / "pdf.ttf", languages_dir / "pdf.ttf")
        data_path = traineddata_path()
        if data_path.exists():
            shutil.copy(data_path, languages_dir / data_path.name)
        # The pipeline caches language data in TMP_DIRECTORY across
        # invocations; clear it so each run uses the staged data
        shutil.rmtree(self.ocr_main.TMP_DIRECTORY, ignore_errors=True)

    def doc_directory(self, case):
        """The storage directory holding all of a document's files."""
        # DocumentCloud
        from documentcloud.common import path

        return self.media_root / path.path(case["doc_id"])

    def run_case(self, case):
        """Run one test case through the pipeline.  Returns the merged
        database-facing metadata captured from the API callbacks."""
        # DocumentCloud
        from documentcloud.common import access_choices, path
        from documentcloud.common.environment import encode_pubsub_data

        doc_id = case["doc_id"]
        slug = case["slug"]
        settings = case.get("settings", {})

        # Stage the input document where an upload would put it
        doc_path = self.media_root / path.doc_path(doc_id, slug)
        shutil.rmtree(self.doc_directory(case), ignore_errors=True)
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(case["input"], doc_path)

        self.callbacks.clear()
        redis = self.utils.get_redis()
        self.utils.clean_up(redis, doc_id)

        # Standard processing, as triggered by an upload
        self.utils.initialize(redis, doc_id)
        self.publisher.publish(
            self.ii_main.PDF_PROCESS_TOPIC,
            encode_pubsub_data(
                {
                    "doc_id": doc_id,
                    "slug": slug,
                    "access": access_choices.PRIVATE,
                    "ocr_code": settings.get("ocr_code", "eng"),
                    "force_ocr": settings.get("force_ocr", False),
                    "ocr_engine": settings.get("ocr_engine", "tess4"),
                }
            ),
        )
        self._drain()

        # Optional second phase: redaction of the processed document
        if case.get("redactions"):
            self.utils.initialize(redis, doc_id)
            self.publisher.publish(
                self.ii_main.REDACT_TOPIC,
                encode_pubsub_data(
                    {
                        "doc_id": doc_id,
                        "slug": slug,
                        "access": access_choices.PRIVATE,
                        "ocr_code": settings.get("ocr_code", "eng"),
                        "redactions": case["redactions"],
                    }
                ),
            )
            self._drain()

        return self.collect_metadata()

    def collect_metadata(self):
        """Merge the captured API callbacks into the final database-facing
        metadata, keeping the raw callback sequence for reference."""
        database = {}
        errors = []
        for callback in self.callbacks:
            if callback["method"] == "patch":
                database.update(callback["json"])
            else:
                errors.append(callback)
        return {
            "database": database,
            "callbacks": self.callbacks + [],
            "errors": errors,
        }
