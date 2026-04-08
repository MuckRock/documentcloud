# Django
from django.db import models
from django.utils.translation import gettext_lazy as _


class CollaboratorAccess(models.IntegerChoices):
    def __new__(cls, value, label=None, api=False):
        obj = int.__new__(cls, value)
        obj._value_ = value
        if label is not None:
            obj._label_ = label
        obj.api = api
        return obj

    # This collaborator has read access
    view = 0, _("View"), True
    # This collaborator can edit the documents in the project
    edit = 1, _("Edit"), True
    # This collaborator can edit the documents and the project itself
    admin = 2, _("Admin"), True