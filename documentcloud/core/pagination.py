# Django
from django.conf import settings
from django.core.paginator import InvalidPage
from rest_framework import pagination
from rest_framework.exceptions import NotFound


class PageNumberPagination(pagination.PageNumberPagination):
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
