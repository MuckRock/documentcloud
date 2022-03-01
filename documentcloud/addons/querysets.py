# Django
from django.conf import settings
from django.db import models


class AddOnQuerySet(models.QuerySet):
    def get_viewable(self, user):
        if user.is_staff or settings.ADDONS_SHOW_ALL:
            return self.all()
        else:
            return self.none()


class AddOnRunQuerySet(models.QuerySet):
    def get_viewable(self, user):
        if user.is_authenticated:
            return self.filter(user=user)
        else:
            return self.none()
