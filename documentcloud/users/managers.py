"""Custom querysets for account app"""

# Django
from django.contrib.auth.models import UserManager as AuthUserManager

# Standard Library
import logging

# DocumentCloud
from documentcloud.users.querysets import UserQuerySet

logger = logging.getLogger(__name__)


class UserManager(AuthUserManager.from_queryset(UserQuerySet)):
    pass
