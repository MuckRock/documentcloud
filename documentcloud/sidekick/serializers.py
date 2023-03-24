# Django
from rest_framework import serializers

# DocumentCloud
from documentcloud.documents.fields import ChoiceField
from documentcloud.sidekick.choices import Status
from documentcloud.sidekick.models import Sidekick


class SidekickSerializer(serializers.ModelSerializer):
    status = ChoiceField(
        Status, read_only=True, help_text=Sidekick._meta.get_field("status").help_text
    )

    class Meta:
        model = Sidekick
        fields = ["status"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Allow writing to status from processing lambda
        context = kwargs.get("context", {})
        request = context.get("request")
        has_request_auth = (
            request and hasattr(request, "auth") and request.auth is not None
        )
        if has_request_auth and "processing" in request.auth.get("permissions", []):
            self.fields["status"].read_only = False
