# Django
from django import forms
from django.contrib.auth.models import AnonymousUser

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


class ModelChoiceFilter(ViewableMixin, django_filters.ModelChoiceFilter):
    widget = forms.TextInput


class ModelMultipleChoiceFilter(
    ViewableMixin, django_filters.ModelMultipleChoiceFilter
):
    widget = django_filters.widgets.CSVWidget
