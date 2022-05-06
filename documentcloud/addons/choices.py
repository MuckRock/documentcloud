# Django
from django.utils.translation import gettext_lazy as _

# Third Party
from djchoices import ChoiceItem, DjangoChoices


class Event(DjangoChoices):
    # pylint: disable=no-init
    # `api` specifies if this attribute should be accessible via the API
    disabled = ChoiceItem(0, _("Disabled"), api=True)
    hourly = ChoiceItem(1, _("Hourly"), api=True)
    daily = ChoiceItem(2, _("Daily"), api=True)
    weekly = ChoiceItem(3, _("Weekly"), api=True)
    upload = ChoiceItem(4, _("Upload"), api=True)
