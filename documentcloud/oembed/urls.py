"""URL mappings for OEmbed app"""

# Django
from django.urls import re_path

# DocumentCloud
from documentcloud.oembed import views

app_name = "oembed"
urlpatterns = [re_path("oembed(?:.json)?/?", views.OEmbedView.as_view(), name="oembed")]
