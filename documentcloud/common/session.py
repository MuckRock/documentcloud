# Third Party
import environ
import requests

env = environ.Env()

# Processing token environment variable
PROCESSING_TOKEN = env.str("PROCESSING_TOKEN")

# Name of authorization field for processing token
PROCESSING_TOKEN_AUTH_FIELD = "processing-token"

session = requests.Session()
session.headers.update(
    {"Authorization": f"{PROCESSING_TOKEN_AUTH_FIELD} {PROCESSING_TOKEN}"}
)
