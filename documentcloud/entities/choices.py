# Django
from django.db import models
from django.utils.translation import gettext_lazy as _


class EntityAccess(models.IntegerChoices):
    def __new__(cls, value, label=None, api=False):
        obj = int.__new__(cls, value)
        obj._value_ = value
        if label is not None:
            obj._label_ = label
        obj.api = api
        return obj
    # pylint:disable=invalid-name
    # Free and public to all.
    public = 0, _("Public"), True
    # Visible to both the owner and her organization.
    private = 2, _("Private"), True
