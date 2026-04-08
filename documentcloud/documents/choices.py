# Django
from django.db import models
from django.utils.translation import gettext_lazy as _

class Access(models.IntegerChoices):
    def __new__(cls, value, label=None, api=False):
        obj = int.__new__(cls, value)
        obj._value_ = value
        if label is not None:
            obj._label_ = label
        obj.api = api
        return obj

    # Free and public to all.
    public = 0, _("Public"), True
    # Visible to both the owner and her organization.
    organization = 1, _("Organization"), True
    # The document is only visible to its owner.
    private = 2, _("Private"), True
    # The document has been taken down (perhaps temporary).
    invisible = 3, _("Invisible"), False


class Status(models.IntegerChoices):
    def __new__(cls, value, label=None, api=False):
        obj = int.__new__(cls, value)
        obj._value_ = value
        if label is not None:
            obj._label_ = label
        obj.api = api
        return obj

    # The document is in a normal successful state
    success = 0, _("Success"), True
    # The document is processing, but readable during the operation
    readable = 1, _("Readable"), True
    # The document is processing, and not currently readable
    pending = 2, _("Pending"), True
    # There was an error processing the document
    error = 3, _("Error"), True
    # There is no file yet
    nofile = 4, _("No file"), True
    # The file is deleted
    deleted = 5, _("Deleted"), False


class EntityKind(models.IntegerChoices):
    def __new__(cls, value, label=None, api=False):
        obj = int.__new__(cls, value)
        obj._value_ = value
        if label is not None:
            obj._label_ = label
        obj.api = api
        return obj

    unknown = 0, _("Unknown"), True
    person = 1, _("Person"), True
    location = 2, _("Location"), True
    organization = 3, _("Organization"), True
    event = 4, _("Event"), True
    work_of_art = 5, _("Work_Of_Art"), True
    consumer_good = 6, _("Consumer_Good"), True
    other = 7, _("Other"), True
    phone_number = 9, _("Phone_Number"), True
    address = 10, _("Address"), True
    date = 11, _("Date"), True
    number = 12, _("Number"), True
    price = 13, _("Price"), True


class OccurrenceKind(models.IntegerChoices):
    def __new__(cls, value, label=None, api=False):
        obj = int.__new__(cls, value)
        obj._value_ = value
        if label is not None:
            obj._label_ = label
        obj.api = api
        return obj

    unknown = 0, _("Unknown"), True
    proper = 1, _("Proper"), True
    common = 2, _("Common"), True