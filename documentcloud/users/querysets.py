"""Custom querysets for users app"""

# Django
from django.db import models
from django.db.models import Prefetch, Q
from django.db.models.expressions import Exists, OuterRef

# Third Party
from squarelet_auth.organizations.models import Membership

# DocumentCloud
from documentcloud.documents.choices import Access
from documentcloud.organizations.models import Organization


class UserQuerySet(models.QuerySet):
    """Custom queryset for users"""

    def get_viewable(self, user):
        """You may view other users in your organizations and projects,
        and anybody with a public document
        """
        # DocumentCloud
        from documentcloud.documents.models import Document

        if user.is_authenticated:
            # unions are much more performant than complex conditions
            return self.annotate(
                public=Exists(
                    Document.objects.filter(
                        user=OuterRef("pk"), access=Access.public
                    ).values("pk")
                )
            ).filter(
                Q(
                    pk__in=self.filter(organizations__in=user.organizations.all())
                    .order_by()
                    .values("pk")
                    .union(
                        self.filter(projects__in=user.projects.all())
                        .order_by()
                        .values("pk")
                    )
                )
                | Q(public=True)
            )
        else:
            return self.annotate(
                public=Exists(
                    Document.objects.filter(
                        user=OuterRef("pk"), access=Access.public
                    ).values("pk")
                )
            ).filter(public=True)

    def preload(self, _user=None, _expand=""):
        """Preload relations"""
        queryset = self.prefetch_related(
            "organizations",
            Prefetch(
                "memberships",
                queryset=Membership.objects.filter(active=True).select_related(
                    "organization__entitlement"
                ),
                to_attr="active_memberships",
            ),
            Prefetch(
                "organizations",
                queryset=Organization.objects.filter(verified_journalist=True),
                to_attr="verified_organizations",
            ),
            Prefetch(
                "organizations",
                queryset=Organization.objects.filter(
                    memberships__admin=True
                ).distinct(),
                to_attr="admin_organizations",
            ),
        )

        return queryset
