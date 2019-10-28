# Standard Library
import base64
import json

# Third Party
import environ

env = environ.Env()

ERROR_IF_NO_TOPIC = True


def encode_pubsub_data(data):
    return json.dumps(data).encode("utf8")


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
            self.tasks[topic_path]({"data": base64.b64encode(data).decode("utf-8")})
        else:
            if ERROR_IF_NO_TOPIC:
                raise ValueError(f"Topic not registered: {topic_path}")


# Define pub sub client and topic subscriptions
publisher = LocalPubSubClient()


def page_image_ready_for_extraction(data):
    from documentcloud.documents.tasks import extract_images

    return extract_images(data)


publisher.register_internal_callback(
    ("documentcloud", "page-image-ready-for-extraction"),
    page_image_ready_for_extraction,
)


def ocr_page_task(data):
    from documentcloud.documents.tasks import ocr_pages

    return ocr_pages.delay(data)


publisher.register_internal_callback(("documentcloud", "ocr-queue"), ocr_page_task)
