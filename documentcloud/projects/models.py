# Django
from django.db import models
from django.utils.translation import ugettext_lazy as _

# Third Party
from autoslug.fields import AutoSlugField

# DocumentCloud
from documentcloud.core.fields import AutoCreatedField, AutoLastModifiedField
from documentcloud.projects.querysets import ProjectQuerySet


class Project(models.Model):
    """A collection of documents which can be collaborated on"""

    objects = ProjectQuerySet.as_manager()

    user = models.ForeignKey(
        verbose_name=_("user"),
        to="users.User",
        on_delete=models.PROTECT,
        related_name="+",
        help_text=_("The user who created this project"),
    )
    title = models.CharField(
        _("title"), max_length=255, blank=True, help_text=_("The title of the project")
    )
    slug = AutoSlugField(
        _("slug"),
        max_length=255,
        populate_from="title",
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

    def __str__(self):
        return self.title if self.title else "-Untitled-"


class ProjectMembership(models.Model):
    """A document belonging to a project"""

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
        default=False,
        help_text=_(
            "Whether collaborators on this project have edit access to this document"
        ),
    )


class Collaboration(models.Model):
    """A user collaborating on a project"""

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

    creator = models.ForeignKey(
        verbose_name=_("creator"),
        to="users.User",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="+",
        help_text=_("The user who created this collaboration"),
    )
