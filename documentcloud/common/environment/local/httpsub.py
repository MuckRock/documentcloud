# Third Party
import environ
import requests_mock

# DocumentCloud
from documentcloud.common.session import session as httpsub

env = environ.Env()


adapter = requests_mock.Adapter()
httpsub.mount("mock", adapter)


def process_callback(request, _context):
    # DocumentCloud
    from documentcloud.documents.processing.utils.main import process_doc

    return process_doc(request.json())


def progress_callback(request, _context):
    # DocumentCloud
    from documentcloud.documents.processing.utils.main import get_progress

    return get_progress(request.json())


def import_callback(request, _context):
    # DocumentCloud
    from documentcloud.documents.processing.utils.main import import_documents

    return import_documents(request.json())


def sidekick_callback(request, _context):
    # DocumentCloud
    from documentcloud.documents.processing.utils.main import sidekick

    return sidekick(request.json())


adapter.register_uri("POST", env("DOC_PROCESSING_URL"), json=process_callback)
adapter.register_uri("POST", env("PROGRESS_URL"), json=progress_callback)
adapter.register_uri("POST", env("IMPORT_URL"), json=import_callback)
adapter.register_uri("POST", env("SIDEKICK_PROCESSING_URL"), json=sidekick_callback)
