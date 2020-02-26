# Django
from django.conf import settings


class OEmbed:
    """Class used to register content to the OEmbed endpoint"""

    patterns = []

    def response(self, request, max_width, max_height, **kwargs):
        raise NotImplementedError("You must implement `response` for OEmbed")

    def oembed(self, **kwargs):
        """Generate the oembed response"""
        oembed = {"version": "1.0"}

        # fetch site wide parameters
        site_parameters = ["provider_name", "provider_url", "cache_age"]
        for parameter in site_parameters:
            setting_name = f"OEMBED_{parameter.upper()}"
            if hasattr(settings, setting_name):
                setting_value = getattr(settings, setting_name)
                if setting_value:
                    oembed[parameter] = setting_value

        # merge in extra parameters explcitly passed in
        oembed.update(kwargs)

        return oembed


class RichOEmbed(OEmbed):
    """OEmbed subclass for the rich OEmbed type"""

    # pylint: disable=abstract-method

    def oembed(self, **kwargs):
        kwargs["type"] = "rich"
        return super().oembed(**kwargs)
