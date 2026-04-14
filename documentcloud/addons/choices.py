# Django
from django.db import models
from django.utils.translation import gettext_lazy as _


class Event(models.IntegerChoices):
    def __new__(cls, value, label=None, api=False):
        obj = int.__new__(cls, value)
        obj._value_ = value
        if label is not None:
            obj._label_ = label
        obj.api = api
        return obj
    # pylint:disable = invalid-name
    disabled = 0, _("Disabled"), True
    hourly = 1, _("Hourly"), True
    daily = 2, _("Daily"), True
    weekly = 3, _("Weekly"), True
    upload = 4, _("Upload"), True
