# Django
from django.utils.translation import gettext_lazy as _

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
    # The file is deleted
    deleted = ChoiceItem(5, _("Deleted"), api=False)


class EntityKind(DjangoChoices):
    # pylint: disable=no-init
    unknown = ChoiceItem(0, _("Unknown"), api=True)
    person = ChoiceItem(1, _("Person"), api=True)
    location = ChoiceItem(2, _("Location"), api=True)
    organization = ChoiceItem(3, _("Organization"), api=True)
    event = ChoiceItem(4, _("Event"), api=True)
    work_of_art = ChoiceItem(5, _("Work_Of_Art"), api=True)
    consumer_good = ChoiceItem(6, _("Consumer_Good"), api=True)
    other = ChoiceItem(7, _("Other"), api=True)
    phone_number = ChoiceItem(9, _("Phone_Number"), api=True)
    address = ChoiceItem(10, _("Address"), api=True)
    date = ChoiceItem(11, _("Date"), api=True)
    number = ChoiceItem(12, _("Number"), api=True)
    price = ChoiceItem(13, _("Price"), api=True)


class OccurrenceKind(DjangoChoices):
    # pylint: disable=no-init
    unknown = ChoiceItem(0, _("Unknown"), api=True)
    proper = ChoiceItem(1, _("Proper"), api=True)
    common = ChoiceItem(2, _("Common"), api=True)
