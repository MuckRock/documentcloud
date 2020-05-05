# Django
from django.db import transaction

# Standard Library
from unittest import mock


def run_commit_hooks():
    """
    Fake transaction commit to run delayed on_commit functions
    https://medium.com/gitux/speed-up-django-transaction-hooks-tests-6de4a558ef96
    """
    with mock.patch(
        "django.db.backends.base.base.BaseDatabaseWrapper.validate_no_atomic_block",
        lambda a: False,
    ):
        transaction.get_connection().run_and_clear_commit_hooks()
