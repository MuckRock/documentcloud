# Django
from django.test.utils import override_settings

# Standard Library
from unittest.mock import patch

# Third Party
import pytest

# DocumentCloud
from documentcloud.addons.tests.factories import AddOnFactory

TOKENS = {"access_token": "access", "refresh_token": "refresh"}


@pytest.mark.django_db()
class TestAddOnTokens:
    """Klaxon's token carries a permission, so that the API can recognize its
    email as coming from Klaxon - the token is all the API ever sees.
    """

    def test_token_permissions_klaxon(self):
        addon = AddOnFactory()
        with override_settings(KLAXON_ADDON_ID=addon.pk):
            assert addon.token_permissions == ["klaxon"]

    def test_token_permissions_other_addon(self):
        addon, klaxon = AddOnFactory.create_batch(2)
        with override_settings(KLAXON_ADDON_ID=klaxon.pk):
            assert addon.token_permissions == []

    @override_settings(KLAXON_ADDON_ID=0)
    def test_token_permissions_unconfigured(self):
        """An unset Klaxon ID must never match an add-on"""
        addon = AddOnFactory()
        assert addon.token_permissions == []

    @override_settings(KLAXON_ADDON_ID=0)
    def test_get_tokens(self, user):
        """An add-on with no permissions asks Squarelet for a plain token"""
        addon = AddOnFactory()
        with patch("documentcloud.addons.models.squarelet_get") as mock_get:
            mock_get.return_value.json.return_value = TOKENS
            assert addon.get_tokens(user) == TOKENS
        mock_get.assert_called_once_with(f"/api/refresh_tokens/{user.uuid}/", params={})

    def test_get_tokens_klaxon(self, user):
        """Klaxon's token is requested with the klaxon permission"""
        addon = AddOnFactory()
        with override_settings(KLAXON_ADDON_ID=addon.pk):
            with patch("documentcloud.addons.models.squarelet_get") as mock_get:
                mock_get.return_value.json.return_value = TOKENS
                assert addon.get_tokens(user) == TOKENS
        mock_get.assert_called_once_with(
            f"/api/refresh_tokens/{user.uuid}/", params={"permissions": "klaxon"}
        )
