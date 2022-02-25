# Django
from rest_framework import versioning
from rest_framework.utils.urls import remove_query_param, replace_query_param


class QueryParameterVersioning(versioning.QueryParameterVersioning):
    # pylint: disable=redefined-builtin
    def reverse(
        self, viewname, args=None, kwargs=None, request=None, format=None, **extra
    ):
        url = super().reverse(viewname, args, kwargs, request, format, **extra)
        if request.version == self.default_version:
            return remove_query_param(url, self.version_param)
        if request.version is not None:
            return replace_query_param(url, self.version_param, request.version)
        return url
