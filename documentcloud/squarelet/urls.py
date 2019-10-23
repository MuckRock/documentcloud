"""URL mappings for squarelet app"""

# Django
from django.urls import path

# DocumentCloud
from documentcloud.squarelet import views

app_name = "squarelet"
urlpatterns = [path("webhook/", views.webhook, name="webhook")]
