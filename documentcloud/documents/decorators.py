# Django
from django.conf import settings
from django.utils.cache import patch_cache_control
from django.views.decorators.vary import vary_on_cookie

# Standard Library
from functools import wraps


def conditional_cache_control(**kwargs):
    """Only applies patch_cache_control if the response has no Cache-Control header
    Allows for settings defaults in a viewset that can be overridden on
    a method by method basis
    """

    def _cache_controller(viewfunc):
        @wraps(viewfunc)
        def _cache_controlled(request, *args, **kw):
            response = viewfunc(request, *args, **kw)
            if "Cache-Control" not in response:
                patch_cache_control(response, **kwargs)
            return response

        return _cache_controlled

    return _cache_controller


def anonymous_cache_control(viewfunc):
    """Cache this view only if the user is anonymous"""

    @wraps(viewfunc)
    @vary_on_cookie
    def inner(request, *args, **kwargs):
        response = viewfunc(request, *args, **kwargs)
        has_auth_token = hasattr(request, "auth") and request.auth is not None
        if has_auth_token or request.user.is_authenticated:
            patch_cache_control(response, private=True, no_cache=True)
        else:
            patch_cache_control(
                response, public=True, max_age=settings.CACHE_CONTROL_MAX_AGE
            )
        return response

    return inner
