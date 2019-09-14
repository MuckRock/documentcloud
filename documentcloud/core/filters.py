# Django
from django import forms

# Third Party
import django_filters


class ModelChoiceFilter(django_filters.ModelChoiceFilter):
    def __init__(self, *args, **kwargs):
        model = kwargs.pop("model")
        super().__init__(
            queryset=model.objects.all(), widget=forms.TextInput, *args, **kwargs
        )
