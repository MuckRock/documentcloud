import environ

env = environ.Env()

# Whether to throw an error if a URL is requested that is not registered.
ERROR_IF_NO_URL = True


class HTTPSub:
    def __init__(self):
        self.tasks = {}

    def register_internal_route(self, url, callback_fn):
        self.tasks[url] = callback_fn

    def post(self, url, json):
        if url in self.tasks:
            self.tasks[url](json)
        else:
            if ERROR_IF_NO_URL:
                raise ValueError(f"HTTP route not registered: {url}")


# Define http sub client and subscriptions
httpsub = HTTPSub()


def process_file_task(data):
    from documentcloud.documents.tasks import process_file

    return process_file.delay(data)


httpsub.register_internal_route(env.str("DOC_PROCESSING_URL"), process_file_task)