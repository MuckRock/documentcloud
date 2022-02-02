# Django
from django.conf import settings
from django.core.paginator import InvalidPage, Paginator
from django.db import OperationalError, connection, transaction
from django.utils.functional import cached_property
from rest_framework import pagination
from rest_framework.exceptions import NotFound


class PageNumberPagination(pagination.PageNumberPagination):
    """For DRF"""

    page_size = 25
    page_size_query_param = "per_page"
    max_page_size = 100
    auth_page_limit = settings.AUTH_PAGE_LIMIT
    anon_page_limit = settings.ANON_PAGE_LIMIT

    def paginate_queryset(self, queryset, request, view=None):
        """
        Paginate a queryset if required, either returning a
        page object, or `None` if pagination is not configured for this view.
        """
        page_size = self.get_page_size(request)
        if not page_size:
            return None

        paginator = self.django_paginator_class(queryset, page_size)
        page_limit = (
            self.auth_page_limit
            if request.user.is_authenticated
            else self.anon_page_limit
        )
        page_number = request.query_params.get(self.page_query_param, 1)
        try:
            page_number = int(page_number)
        except (TypeError, ValueError):
            msg = self.invalid_page_message.format(
                page_number=page_number, message="That page number is not an integer"
            )
            raise NotFound(msg)

        if page_number > page_limit:
            msg = self.invalid_page_message.format(
                page_number=page_number, message="That page is past the limit"
            )
            raise NotFound(msg)

        try:
            self.page = paginator.page(page_number)
        except InvalidPage as exc:
            msg = self.invalid_page_message.format(
                page_number=page_number, message=str(exc)
            )
            raise NotFound(msg)

        if paginator.num_pages > 1 and self.template is not None:
            # The browsable API should display pagination controls.
            self.display_page_controls = True

        self.request = request
        return list(self.page)


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
                # If any other exception occurred fall back to default behaviour
                pass
        return super().count
