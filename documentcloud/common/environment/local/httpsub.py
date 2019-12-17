# Third Party
import environ
import requests
import requests_mock

env = environ.Env()


# Define http sub client and subscriptions
httpsub = requests.Session()
adapter = requests_mock.Adapter()
httpsub.mount("mock", adapter)


def process_callback(request, _context):
    from documentcloud.documents.processing.utils.main import process_pdf

    return process_pdf(request.json())


def progress_callback(request, _context):
    from documentcloud.documents.processing.utils.main import get_progress

    return get_progress(request.json())


adapter.register_uri("POST", env("DOC_PROCESSING_URL"), json=process_callback)
adapter.register_uri("POST", env("PROGRESS_URL"), json=progress_callback)
