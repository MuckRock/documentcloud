# Standard Library
from functools import wraps


def skip_if_not_obj(func):
    """Decorator for predicates
    Skip the predicate if obj is None"""

    @wraps(func)
    def inner(user, obj):
        if obj is None:
            return None
        else:
            return func(user, obj)

    return inner
