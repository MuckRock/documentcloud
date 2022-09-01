# Django
from django.utils.translation import gettext_lazy as _

# Third Party
from djchoices import ChoiceItem, DjangoChoices


class Status(DjangoChoices):
    success = ChoiceItem(0, _("Success"), api=True)
    pending = ChoiceItem(1, _("Pending"), api=True)
    error = ChoiceItem(2, _("Error"), api=True)
