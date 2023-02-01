# Django
from django.utils.translation import gettext_lazy as _

# Third Party
from djchoices import ChoiceItem, DjangoChoices


class EntityAccess(DjangoChoices):
    # `api` specifies if this attribute should be accessible via the API
    # Free and public to all.
    public = ChoiceItem(0, _("Public"), api=True)
    # Visible to both the owner and her organization.
    private = ChoiceItem(2, _("Private"), api=True)
