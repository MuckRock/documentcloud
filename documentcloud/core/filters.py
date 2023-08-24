# Django
from django import forms
from django.contrib.auth.models import AnonymousUser
from django.utils.datastructures import MultiValueDict

# Third Party
import django_filters


class ViewableMixin:
    def __init__(self, *args, **kwargs):
        model = kwargs.pop("model")

        def get_viewable(request):
            if request is None:
                user = AnonymousUser()
            else:
                user = request.user

            return model.objects.get_viewable(user)

        super().__init__(queryset=get_viewable, widget=self.widget, *args, **kwargs)


class QueryArrayWidget(django_filters.widgets.BaseCSVWidget, forms.TextInput):
    """
    This is a copy of the implementation provided by django-filters which attempts
    to fix the following issue:
    https://github.com/carltongibson/django-filter/issues/1090#issuecomment-506477491

    Enables request query array notation that might be consumed by MultipleChoiceFilter

    1. Values can be provided as csv string:  ?foo=bar,baz
    2. Values can be provided as query array: ?foo[]=bar&foo[]=baz
    3. Values can be provided as query array: ?foo=bar&foo=baz

    Note: Duplicate and empty values are skipped from results
    """

    def value_from_datadict(self, data, files, name):

        if not isinstance(data, MultiValueDict):
            data = MultiValueDict(data)

        values_list = data.getlist(name, data.getlist(f"{name}[]")) or []

        # apparently its an array, so no need to process it's values as csv
        # ?foo=1&foo=2 -> data.getlist(foo) -> foo = [1, 2]
        # ?foo[]=1&foo[]=2 -> data.getlist(foo[]) -> foo = [1, 2]
        if len(values_list) > 1:
            ret = [x for x in values_list if x]
        elif len(values_list) == 1:
            # treat first element as csv string
            # ?foo=1,2 -> data.getlist(foo) -> foo = ['1,2']
            ret = [x.strip() for x in values_list[0].rstrip(",").split(",") if x]
        else:
            ret = []

        return list(set(ret))


class ModelChoiceFilter(ViewableMixin, django_filters.ModelChoiceFilter):
    widget = forms.TextInput


class ModelMultipleChoiceFilter(
    ViewableMixin, django_filters.ModelMultipleChoiceFilter
):
    widget = QueryArrayWidget


class ChoicesFilter(django_filters.TypedMultipleChoiceFilter):
    """A choices filter configured to work how we want our choice filters to work
    `choices` kwarg should be an instanceof DjangoChoices
    """

    def __init__(self, *args, **kwargs):
        choices = kwargs.pop("choices")
        kwargs["choices"] = list(choices.labels.items())
        kwargs["coerce"] = lambda x: getattr(choices, x)
        kwargs["widget"] = QueryArrayWidget
        super().__init__(*args, **kwargs)
