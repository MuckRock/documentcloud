# Django
from django.db import models
from django.db.models import Q

# DocumentCloud
from documentcloud.documents.choices import Access


class AddOnQuerySet(models.QuerySet):
    def get_viewable(self, user):
        if user.is_authenticated:
            return self.filter(
                Q(access=Access.public)
                | Q(github_account__user=user)
                | Q(
                    access=Access.organization,
                    organization__in=user.organizations.all(),
                ),
                removed=False,
            )
        else:
            return self.filter(access=Access.public, removed=False)


class AddOnRunQuerySet(models.QuerySet):
    def get_viewable(self, user):
        if user.is_authenticated:
            return self.filter(user=user)
        else:
            return self.none()


class AddOnEventQuerySet(models.QuerySet):
    def get_viewable(self, user):
        if user.is_authenticated:
            return self.filter(user=user)
        else:
            return self.none()


class VisualAddOnQuerySet(models.QuerySet):
    def get_viewable(self, user):
        if user.is_authenticated:
            return self.filter(
                Q(access=Access.public)
                | Q(user=user)
                | Q(
                    access=Access.organization,
                    organization__in=user.organizations.all(),
                ),
            )
        else:
            return self.filter(access=Access.public)
