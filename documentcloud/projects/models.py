# Django
from django.db import models
from django.utils.translation import gettext_lazy as _

# Third Party
from django_extensions.db.fields import AutoSlugField

# DocumentCloud
from documentcloud.core.fields import AutoCreatedField, AutoLastModifiedField
from documentcloud.core.utils import slugify
from documentcloud.projects.choices import CollaboratorAccess
from documentcloud.projects.querysets import (
    CollaborationQuerySet,
    ProjectMembershipQuerySet,
    ProjectQuerySet,
)


class Project(models.Model):
    """A collection of documents which can be collaborated on"""

    objects = ProjectQuerySet.as_manager()

    user = models.ForeignKey(
        verbose_name=_("user"),
        to="users.User",
        on_delete=models.PROTECT,
        related_name="+",
        # This is set to false so we can import projects before their
        # owners
        # Once migration from old DocumentCloud is complete, this should
        # be set back to True
        db_constraint=False,
        help_text=_("The user who created this project"),
    )
    title = models.CharField(
        _("title"), max_length=255, blank=True, help_text=_("The title of the project")
    )
    slug = AutoSlugField(
        _("slug"),
        max_length=255,
        populate_from="title",
        allow_duplicates=True,
        slugify_function=slugify,
        help_text=_("A slug for the project which may be used in a URL"),
    )
    description = models.TextField(
        _("description"),
        blank=True,
        help_text=("A description of the documents contained in this project"),
    )
    private = models.BooleanField(
        _("private"),
        default=False,
        help_text=_("Private projects may only be viewed by their collaborators"),
    )

    documents = models.ManyToManyField(
        verbose_name=_("documents"),
        to="documents.Document",
        through="projects.ProjectMembership",
        related_name="projects",
        help_text=_("The documents in this project"),
    )
    collaborators = models.ManyToManyField(
        verbose_name=_("collaborators"),
        to="users.User",
        through="projects.Collaboration",
        related_name="projects",
        through_fields=("project", "user"),
    )

    created_at = AutoCreatedField(
        _("created at"), help_text=_("Timestamp of when the project was created")
    )
    updated_at = AutoLastModifiedField(
        _("updated at"), help_text=_("Timestamp of when the project was last updated")
    )

    class Meta:
        ordering = ("slug",)
        permissions = (
            ("add_remove_project", "Can add & remove documents from a project"),
        )

    def __str__(self):
        return self.title if self.title else "-Untitled-"

    def get_absolute_url(self):
        # Opposite order of doc url (for legacy reasons)
        return f"/projects/{self.slug}-{self.pk}/"


class ProjectMembership(models.Model):
    """A document belonging to a project"""

    objects = ProjectMembershipQuerySet.as_manager()

    project = models.ForeignKey(
        verbose_name=_("project"),
        to="projects.Project",
        on_delete=models.CASCADE,
        help_text=_("The project which contains the document"),
    )
    document = models.ForeignKey(
        verbose_name=_("document"),
        to="documents.Document",
        on_delete=models.CASCADE,
        help_text=_("The document which belongs to the project"),
    )
    edit_access = models.BooleanField(
        verbose_name=_("edit access"),
        default=True,
        help_text=_(
            "Whether collaborators on this project have edit access to this document"
        ),
    )

    class Meta:
        ordering = ("id",)
        unique_together = ("project", "document")


class Collaboration(models.Model):
    """A user collaborating on a project"""

    objects = CollaborationQuerySet.as_manager()

    project = models.ForeignKey(
        verbose_name=_("project"),
        to="projects.Project",
        on_delete=models.CASCADE,
        help_text=_("The project being collaborated on"),
    )
    user = models.ForeignKey(
        verbose_name=_("user"),
        to="users.User",
        on_delete=models.CASCADE,
        help_text=_("The user collaborating on this project"),
    )
    access = models.IntegerField(
        _("access"),
        choices=CollaboratorAccess.choices,
        default=CollaboratorAccess.view,
        help_text=_("The level of access granted to this collaborator"),
    )

    creator = models.ForeignKey(
        verbose_name=_("creator"),
        to="users.User",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="+",
        help_text=_("The user who created this collaboration"),
    )

    class Meta:
        ordering = ("id",)
        unique_together = ("project", "user")
