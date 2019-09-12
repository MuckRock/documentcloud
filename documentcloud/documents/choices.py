# Django
from django.utils.translation import ugettext_lazy as _

# Third Party
from djchoices import ChoiceItem, DjangoChoices


class Access(DjangoChoices):
    # pylint: disable=no-init
    # Free and public to all.
    public = ChoiceItem(0, _("Public"))
    # Visible to both the owner and her organization.
    organization = ChoiceItem(1, _("Organization"))
    # The document is only visible to its owner.
    private = ChoiceItem(2, _("Private"))
    # The document has been taken down (perhaps temporary).
    invisible = ChoiceItem(3, _("Invisible"))


class Status(DjangoChoices):
    # pylint: disable=no-init
    # The document is in a normal succesful state
    success = ChoiceItem(0, _("Success"))
    # The document is processing, but readable during the operation
    readable = ChoiceItem(1, _("Readable"))
    # The document is processing, and not currently readable
    pending = ChoiceItem(2, _("Pending"))
    # There was an error processing the document
    error = ChoiceItem(3, _("Error"))
