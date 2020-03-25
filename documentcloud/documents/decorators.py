# Django
from django.utils.cache import patch_cache_control

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
