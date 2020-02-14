# Third Party
import factory

# DocumentCloud
from documentcloud.projects.choices import CollaboratorAccess
from documentcloud.projects.models import Collaboration, ProjectMembership


class ProjectFactory(factory.django.DjangoModelFactory):
    """A factory for creating Project test objects"""

    user = factory.SubFactory("documentcloud.users.tests.factories.UserFactory")
    title = factory.Sequence(lambda n: f"Project {n}")
    description = factory.Faker("text")

    class Meta:
        model = "projects.Project"

    @factory.post_generation
    def documents(project, create, extracted, **kwargs):
        # pylint: disable=unused-argument
        ProjectFactory._documents(project, create, extracted, edit_access=False)

    @factory.post_generation
    def edit_documents(project, create, extracted, **kwargs):
        # pylint: disable=unused-argument
        ProjectFactory._documents(project, create, extracted, edit_access=True)

    @staticmethod
    def _documents(project, create, extracted, edit_access):
        if create and extracted:
            for document in extracted:
                ProjectMembership.objects.create(
                    document=document, project=project, edit_access=edit_access
                )

    @factory.post_generation
    def admin_collaborators(project, create, extracted, **kwargs):
        # pylint: disable=unused-argument
        if create:
            # Make the owner an admin collaborator by default
            extracted = extracted or []
            extracted.append(project.user)
        ProjectFactory._collaborators(
            project, create, extracted, CollaboratorAccess.admin
        )

    @factory.post_generation
    def edit_collaborators(project, create, extracted, **kwargs):
        # pylint: disable=unused-argument
        ProjectFactory._collaborators(
            project, create, extracted, CollaboratorAccess.edit
        )

    @factory.post_generation
    def collaborators(project, create, extracted, **kwargs):
        # pylint: disable=unused-argument
        ProjectFactory._collaborators(
            project, create, extracted, CollaboratorAccess.view
        )

    @staticmethod
    def _collaborators(project, create, extracted, access):
        # pylint: disable=unused-argument
        if create and extracted:
            for user in extracted:
                Collaboration.objects.create(user=user, project=project, access=access)
