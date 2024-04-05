# Django
from django.conf import settings
from django.core.cache import cache
from django.http.response import JsonResponse

# Standard Library
import logging

# Third Party
from ipware import get_client_ip

logger = logging.getLogger(__name__)


class LogHTTPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger("http_requests")

    def __call__(self, request):

        try:
            request.log_body = request.body
        except:  # pylint: disable=bare-except
            request.log_body = None

        response = self.get_response(request)

        self.logger.info(
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


class RateLimitAnonymousUsers:
    """Rate limit anonymous users to encourage people to login"""

    def __init__(self, get_response):
        self.get_response = get_response

        # how many requests to allow per time period
        self.limit = settings.ANON_RL_LIMIT
        self.timeout = settings.ANON_RL_TIMEOUT

        # paths to exclude from the rate limiting
        # we want to exclude the login path so anonymous users may login
        self.exclude_paths = settings.ANON_RL_EXCLUDE_PATHS

        # the error message to return when rate limited
        self.message = {"message": settings.ANON_RL_MESSAGE}

    def __call__(self, request):

        if request.user.is_authenticated or request.path in self.exclude_paths:
            return self.get_response(request)

        try:
            ip_address, _ = get_client_ip(request)
            key = f"ratelimit-{ip_address}"
            value = cache.incr(key)
            logger.info("[ANON RATE LIMIT] IP: %s - %d", ip_address, value)
            if value > self.limit:
                return JsonResponse(self.message, status=429)
        except ValueError:
            logger.info("[ANON RATE LIMIT] New IP: %s", ip_address)
            cache.set(key, 1, timeout=self.timeout)

        return self.get_response(request)
