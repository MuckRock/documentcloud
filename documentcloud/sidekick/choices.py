# Django
from django.utils.translation import ugettext_lazy as _

# Third Party
from djchoices import ChoiceItem, DjangoChoices


class Status(DjangoChoices):
    # pylint: disable=no-init
    uninitialized = ChoiceItem(0, _("Uninitialized"))
    processing = ChoiceItem(1, _("Processing"))
    initialized = ChoiceItem(2, _("Initialized"))
    error = ChoiceItem(3, _("Error"))
