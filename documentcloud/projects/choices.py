# Django
from django.utils.translation import gettext_lazy as _

# Third Party
from djchoices import ChoiceItem, DjangoChoices


class CollaboratorAccess(DjangoChoices):
    # pylint: disable=no-init
    # `api` specifies if this attribute should be accessible via the API
    # This collaborator has read access
    view = ChoiceItem(0, _("View"), api=True)
    # This collaborator can edit the documents in the project
    edit = ChoiceItem(1, _("Edit"), api=True)
    # This collaborator  can edit the documents and the project itself
    admin = ChoiceItem(2, _("Admin"), api=True)
