# Standard Library
import base64
import json

# Third Party
import environ

env = environ.Env()

ERROR_IF_NO_TOPIC = True


def encode_pubsub_data(data):
    return json.dumps(data).encode("utf8")


def encode_published_pubsub_data(data):
    return {"data": base64.b64encode(data).decode("utf-8")}


def decode_pubsub_data(data):
    return json.loads(base64.b64decode(data["data"]).decode("utf-8"))


class LocalPubSubClient:
    def __init__(self):
        self.tasks = {}

    @staticmethod
    def topic_path(namespace, name):
        return (namespace, name)

    def register_internal_callback(self, topic_path, callback_fn):
        self.tasks[topic_path] = callback_fn

    def publish(self, topic_path, data):
        if topic_path in self.tasks:
            self.tasks[topic_path](encode_published_pubsub_data(data))
        else:
            if ERROR_IF_NO_TOPIC:
                raise ValueError(f"Topic not registered: {topic_path}")


# Define pub sub client and topic subscriptions
publisher = LocalPubSubClient()


def process_pdf_task(data):
    from documentcloud.documents.tasks import process_file_internal

    return process_file_internal.delay(data)


def document_convert_task(data):
    from documentcloud.documents.tasks import document_convert

    return document_convert.delay(data)


def page_cache_task(data):
    from documentcloud.documents.tasks import cache_pages

    return cache_pages.delay(data)


def extract_image_task(data):
    from documentcloud.documents.tasks import extract_images

    return extract_images.delay(data)


def ocr_page_task(data):
    from documentcloud.documents.tasks import ocr_pages

    return ocr_pages.delay(data)


def assemble_text_task(data):
    from documentcloud.documents.tasks import assemble_text

    return assemble_text.delay(data)


def extract_text_position_task(data):
    from documentcloud.documents.tasks import text_position_extract

    return text_position_extract.delay(data)


def redact_doc_task(data):
    from documentcloud.documents.tasks import redact_document

    return redact_document.delay(data)


def modify_doc_task(data):
    from documentcloud.documents.tasks import modify_document

    return modify_document.delay(data)


def start_import_task(data):
    from documentcloud.documents.tasks import start_import_process

    return start_import_process.delay(data)


def import_document_task(data):
    from documentcloud.documents.tasks import import_doc

    return import_doc.delay(data)


def finish_import_task(data):
    from documentcloud.documents.tasks import finish_import_process

    return finish_import_process.delay(data)


def sidekick_preprocess_task(data):
    from documentcloud.sidekick.tasks import sidekick_preprocess

    return sidekick_preprocess.delay(data)


publisher.register_internal_callback(
    ("documentcloud", env.str("PDF_PROCESS_TOPIC", default="pdf-process")),
    process_pdf_task,
)
publisher.register_internal_callback(
    ("documentcloud", env.str("DOCUMENT_CONVERT_TOPIC", default="document-convert")),
    document_convert_task,
)
publisher.register_internal_callback(
    ("documentcloud", env.str("PAGE_CACHE_TOPIC", default="page-cache")),
    page_cache_task,
)
publisher.register_internal_callback(
    ("documentcloud", env.str("IMAGE_EXTRACT_TOPIC", default="image-extraction")),
    extract_image_task,
)
publisher.register_internal_callback(
    ("documentcloud", env.str("OCR_TOPIC", default="ocr-extraction-dev")), ocr_page_task
)
publisher.register_internal_callback(
    ("documentcloud", env.str("ASSEMBLE_TEXT_TOPIC", default="assemble-text")),
    assemble_text_task,
)
publisher.register_internal_callback(
    (
        "documentcloud",
        env.str("TEXT_POSITION_EXTRACT_TOPIC", default="text-position-extraction"),
    ),
    extract_text_position_task,
)
publisher.register_internal_callback(
    ("documentcloud", env.str("REDACT_TOPIC", default="redact-doc")), redact_doc_task
)
publisher.register_internal_callback(
    ("documentcloud", env.str("MODIFY_TOPIC", default="modify-doc")), modify_doc_task
)
publisher.register_internal_callback(
    ("documentcloud", env.str("START_IMPORT_TOPIC", default="start-import")),
    start_import_task,
)
publisher.register_internal_callback(
    ("documentcloud", env.str("IMPORT_DOCUMENT_TOPIC", default="import-document")),
    import_document_task,
)
publisher.register_internal_callback(
    ("documentcloud", env.str("FINISH_IMPORT_TOPIC", default="finish-import")),
    finish_import_task,
)
publisher.register_internal_callback(
    (
        "documentcloud",
        env.str("SIDEKICK_PREPROCESS_TOPIC", default="sidekick-preprocess-topic"),
    ),
    sidekick_preprocess_task,
)
