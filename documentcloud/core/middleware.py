# Third Party
import django_cprofile_middleware.middleware


class ProfilerMiddleware(django_cprofile_middleware.middleware.ProfilerMiddleware):
    """Subclass cProfile midleware to not check for settings.DEBUG"""

    def can(self, request):
        """Ensure user is staff"""
        return (request.user and request.user.is_staff) and "prof" in request.GET
