def processing_auth(_func):
    """Authenticate a function by ensuring the processing token matches."""

    def authenticate_token(*args, **kwargs):
        raise NotImplementedError("Need to implement on GCP")

    return authenticate_token
