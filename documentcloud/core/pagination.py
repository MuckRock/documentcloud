# Django
from django.conf import settings
from django.core.paginator import Paginator
from django.db import OperationalError, connection, transaction
from django.utils.functional import cached_property
from rest_framework import pagination
from rest_framework.response import Response

# Standard Library
from collections import OrderedDict


class CursorPagination(pagination.CursorPagination):
    ordering = "pk"
    page_size = settings.DEFAULT_PAGE_SIZE
    max_page_size = settings.MAX_PAGE_SIZE
    page_size_query_param = "per_page"


class CursorCountPagination(CursorPagination):
    """Cursor pagination which also returns a count"""

    def paginate_queryset(self, queryset, request, view=None):
        """Do the count here"""
        self.count = queryset.count()
        return super().paginate_queryset(queryset, request, view)

    def get_paginated_response(self, data):
        """Add the count back in for the response"""
        return Response(
            OrderedDict(
                [
                    ("count", self.count),
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                    ("results", data),
                ]
            )
        )

    def _get_position_from_instance(self, instance, ordering):
        """Allow for nested fields to be used for ordering"""
        field_names = ordering[0].lstrip("-").split("__")
        attr = instance
        for field_name in field_names:
            if isinstance(attr, dict):
                attr = attr[field_name]
            else:
                attr = getattr(attr, field_name)
        return str(attr)


class NoCountPaginator(Paginator):
    """For the admin where count is too slow"""

    # https://pganalyze.com/blog/pagination-django-postgres

    @cached_property
    def count(self):
        return 9999999999


class LargeTablePaginator(Paginator):
    """
    Combination of ideas from:
     - https://gist.github.com/safar/3bbf96678f3e479b6cb683083d35cb4d
     - https://medium.com/@hakibenita/optimizing-django-admin-paginator-53c4eb6bfca3

    Overrides the count method of QuerySet objects to avoid timeouts.
    - Try to get the real count limiting the queryset execution time to 150 ms.
    - If count takes longer than 150 ms the database kills the query and raises
    OperationError. In that case, get an estimate instead of actual count when not
    filtered (this estimate can be stale and hence not fit for situations where the
    count of objects actually matter).
    - If any other exception occured fall back to default behaviour.
    """

    # https://gist.githubusercontent.com/noviluni/d86adfa24843c7b8ed10c183a9df2afe/
    # raw/c12dffa5752f6db6d58c2eafac5a87d3cd1c833d/paginator.py

    @cached_property
    def count(self):
        """
        Returns an estimated number of objects, across all pages.
        """
        try:
            with transaction.atomic(), connection.cursor() as cursor:
                # Limit to 150 ms
                cursor.execute("SET LOCAL statement_timeout TO 150;")
                return super().count
        except OperationalError:
            pass

        if not self.object_list.query.where:
            try:
                with transaction.atomic(), connection.cursor() as cursor:
                    # Obtain estimated values (only valid with PostgreSQL)
                    cursor.execute(
                        "SELECT reltuples FROM pg_class WHERE relname = %s",
                        [self.object_list.query.model._meta.db_table],
                    )
                    estimate = int(cursor.fetchone()[0])
                    return estimate
            except Exception:  # pylint: disable=broad-except
                # If any other exception occurred fall back to large number
                pass
        return 9999999999
