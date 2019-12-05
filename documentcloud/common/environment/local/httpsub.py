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
    from documentcloud.documents.processing.info_and_image.main import process_pdf

    return process_pdf(request.json())


adapter.register_uri("POST", env("DOC_PROCESSING_URL"), json=process_callback)
