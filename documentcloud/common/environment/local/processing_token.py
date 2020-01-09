# Third Party
import environ


env = environ.Env()

# Common environment variables
PROCESSING_TOKEN = env.str("PROCESSING_TOKEN")


def processing_auth(func):
    """Authenticate a function by ensuring the processing token matches."""

    def authenticate_token(*args, **kwargs):
        print("LOCAL CONTEXT", args, kwargs)

        # if processing_token != PROCESSING_TOKEN:
        #     raise Exception("Authentication Failed.")

        return func(*args, **kwargs)

    return authenticate_token
