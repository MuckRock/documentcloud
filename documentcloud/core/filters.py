# Django
from django import forms
from django.contrib.auth.models import AnonymousUser

# Third Party
import django_filters


class ModelChoiceFilter(django_filters.ModelChoiceFilter):
    def __init__(self, *args, **kwargs):
        model = kwargs.pop("model")

        def get_viewable(request):
            if request is None:
                user = AnonymousUser()
            else:
                user = request.user

            return model.objects.get_viewable(user)

        super().__init__(queryset=get_viewable, widget=forms.TextInput, *args, **kwargs)
