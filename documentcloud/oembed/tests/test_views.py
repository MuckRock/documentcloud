# Django
from rest_framework import status

# Standard Library
import re

# Third Party
import pytest

# DocumentCloud
from documentcloud.oembed.oembed import OEmbed
from documentcloud.oembed.registry import register
from documentcloud.projects.oembed import ProjectOEmbed
from documentcloud.projects.tests.factories import ProjectFactory


@register
class TestOEmbed(OEmbed):
    patterns = [re.compile(r"https://www.example.com/(?P<pk>[0-9]+)/")]

    def response(self, request, query, max_width, max_height, **kwargs):
        return {
            "query": str(query),
            "max_width": max_width,
            "max_height": max_height,
            "kwargs": kwargs,
        }


@pytest.mark.django_db()
class TestOEmbedView:
    def test_good(self, client):
        """Test a simple oembed call"""
        response = client.get(
            "/api/oembed/", {"url": "https://www.example.com/1/?_escaped_fragment_"}
        )
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert response_json["query"] == "embed=1"
        assert response_json["max_width"] is None
        assert response_json["max_height"] is None
        assert response_json["kwargs"] == {"pk": "1"}

    def test_no_url(self, client):
        """Test a oembed call without specifying a URL"""
        response = client.get("/api/oembed/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_options(self, client):
        """Test an oembed call with options"""
        response = client.get(
            "/api/oembed/",
            {
                "url": "https://www.example.com/1/?embed=1&option=true",
                "maxwidth": 100,
                "maxheight": 200,
            },
        )
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert response_json["query"] == "embed=1&option=true"
        assert response_json["max_width"] == 100
        assert response_json["max_height"] == 200

    def test_bad_dimensions(self, client):
        """Test an oembed call with non integer dimensions"""
        response = client.get(
            "/api/oembed/",
            {
                "url": "https://www.example.com/1/",
                "maxwidth": "foo",
                "maxheight": "bar",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert response_json["max_width"] is None
        assert response_json["max_height"] is None

    def test_404(self, client):
        """Test an oembed call with a non-matching URL"""
        response = client.get("/api/oembed/", {"url": "https://www.example.com/foo/"})
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db()
class TestProjectOEmbedView:

    @pytest.mark.parametrize("title", ["Test", "123-Test", "Test-456", "789-Test-123"])
    @pytest.mark.parametrize("url_t", ["{pk}", "{slug}-{pk}", "{pk}-{slug}"])
    def test(self, client, title, url_t):
        """Test project oembed view"""

        proj = ProjectFactory.create(title=title)
        url = "https://www.documentcloud.org/projects/" + url_t.format(
            pk=proj.pk, slug=proj.slug
        )
        response = client.get(
            "/api/oembed/",
            {"url": url},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["title"] == proj.title
