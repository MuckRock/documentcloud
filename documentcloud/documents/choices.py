# Django
from django.utils.translation import ugettext_lazy as _

# Third Party
from djchoices import ChoiceItem, DjangoChoices


class Access(DjangoChoices):
    # pylint: disable=no-init
    # `api` specifies if this attribute should be accessible via the API
    # Free and public to all.
    public = ChoiceItem(0, _("Public"), api=True)
    # Visible to both the owner and her organization.
    organization = ChoiceItem(1, _("Organization"), api=True)
    # The document is only visible to its owner.
    private = ChoiceItem(2, _("Private"), api=True)
    # The document has been taken down (perhaps temporary).
    invisible = ChoiceItem(3, _("Invisible"), api=False)


class Status(DjangoChoices):
    # pylint: disable=no-init
    # `api` specifies if this attribute should be accessible via the API
    # The document is in a normal succesful state
    success = ChoiceItem(0, _("Success"), api=True)
    # The document is processing, but readable during the operation
    readable = ChoiceItem(1, _("Readable"), api=True)
    # The document is processing, and not currently readable
    pending = ChoiceItem(2, _("Pending"), api=True)
    # There was an error processing the document
    error = ChoiceItem(3, _("Error"), api=True)
    # There is no file yet
    nofile = ChoiceItem(4, _("No file"), api=True)
    # There is no file yet
    deleted = ChoiceItem(5, _("Deleted"), api=False)
