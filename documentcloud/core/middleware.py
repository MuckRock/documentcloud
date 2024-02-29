# Standard Library
import logging

logger = logging.getLogger("http_requests")


class LogHTTPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        try:
            request.log_body = request.body
        except:  # pylint: disable=bare-except
            request.log_body = None

        response = self.get_response(request)

        logger.info(
            "%s %s",
            request.method,
            request.path,
            extra={
                "request": self.format_request(request),
                "response": self.format_response(response),
            },
        )

        return response

    def format_request(self, request):
        """Format a request for logging"""
        if request.log_body:
            body = request.log_body.decode("utf8")[:1024]
        else:
            body = ""
        return {
            "user": self.format_user(request.user),
            "path": request.path,
            "method": request.method,
            "headers": dict(request.headers),
            "get": dict(request.GET),
            "body": body,
        }

    def format_user(self, user):
        """Format a user for logging"""
        if user.is_authenticated:
            return {
                "id": user.pk,
                "username": user.username,
                "name": user.name,
                "email": user.email,
                "organization": self.format_organization(user.organization),
            }

        return None

    def format_organization(self, org):
        """Format an organization for logging"""
        return {
            "id": org.pk,
            "name": org.name,
            "individual": org.individual,
            "verified": org.verified_journalist,
            "plan": org.entitlement.name,
        }

    def format_response(self, response):
        """Format a response for logging"""
        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response.content.decode("utf8")[:1024],
        }
