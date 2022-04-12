# Django
from django.dispatch import receiver

# Standard Library
import logging

# Third Party
from squarelet_auth.users.utils import user_update

# DocumentCloud
from documentcloud.addons.models import GitHubAccount

logger = logging.getLogger(__name__)


@receiver(
    user_update, dispatch_uid="documentcloud.addons.signals.update_github_account"
)
def update_github_account(user, data, **_kwargs):
    """Save the GitHub account information when a user is updated"""
    logger.info("Update GitHub Account information")
    for acct in data.get("social_accounts", []):
        if acct["provider"] != "github_app":
            continue
        if acct["tokens"]:
            token = acct["tokens"][0]["token"]
        else:
            token = ""
        name = acct["extra_data"].get("login", "")
        GitHubAccount.objects.update_or_create(
            uid=acct["uid"], defaults={"user": user, "token": token, "name": name}
        )
