# Third Party
import factory

# DocumentCloud
from documentcloud.projects.models import Collaboration, ProjectMembership


class ProjectFactory(factory.django.DjangoModelFactory):
    """A factory for creating Project test objects"""

    user = factory.SubFactory("documentcloud.users.tests.factories.UserFactory")
    title = factory.Sequence(lambda n: f"Project {n}")
    description = factory.Faker("text")

    class Meta:
        model = "projects.Project"

    @factory.post_generation
    def documents(self, create, extracted, **kwargs):
        # pylint: disable=unused-argument
        if create and extracted:
            for document in extracted:
                ProjectMembership.objects.create(document=document, project=self)

    @factory.post_generation
    def collaborators(self, create, extracted, **kwargs):
        # pylint: disable=unused-argument
        if create:
            # Make the owner a collaborator by default
            Collaboration.objects.create(user=self.user, project=self)
        if create and extracted:
            for user in extracted:
                Collaboration.objects.create(user=user, project=self)
