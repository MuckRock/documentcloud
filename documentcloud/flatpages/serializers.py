# Django
from django.contrib.flatpages.models import FlatPage
from rest_framework import serializers


class FlatPageSerializer(serializers.ModelSerializer):
    class Meta:
        model = FlatPage
        fields = [
            "url",
            "title",
            "content",
        ]
        extra_kwargs = {
            "url": {"help_text": "URL of the flatpage"},
            "title": {"help_text": "Title of the flatpage"},
            "content": {"help_text": "The content of the flatpage"},
        }
