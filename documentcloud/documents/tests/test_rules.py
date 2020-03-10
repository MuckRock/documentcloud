# Django
from django.contrib.auth.models import AnonymousUser

# Third Party
import pytest

# DocumentCloud
from documentcloud.documents.choices import Access, Status
from documentcloud.documents.tests.factories import DocumentFactory, NoteFactory
from documentcloud.organizations.tests.factories import OrganizationFactory
from documentcloud.projects.tests.factories import ProjectFactory
from documentcloud.users.tests.factories import UserFactory


@pytest.mark.django_db()
def test_document_rules():
    # pylint: disable=too-many-locals
    anonymous = AnonymousUser()
    owner = UserFactory()
    edit_collaborator = UserFactory()
    view_collaborator = UserFactory()
    no_access_collaborator = UserFactory()
    organization_member = UserFactory()

    organization = OrganizationFactory(members=[owner, organization_member])
    organization_member.organization = organization

    public_document = DocumentFactory(
        user=owner, organization=organization, access=Access.public, title="public"
    )
    public_pending_document = DocumentFactory(
        user=owner,
        organization=organization,
        access=Access.public,
        status=Status.pending,
        title="pending",
    )
    organization_document = DocumentFactory(
        user=owner, organization=organization, access=Access.organization, title="org"
    )
    private_document = DocumentFactory(
        user=owner, organization=organization, access=Access.private, title="private"
    )
    invisible_document = DocumentFactory(
        user=owner,
        organization=organization,
        access=Access.invisible,
        title="invisible",
    )
    documents = [
        public_document,
        public_pending_document,
        private_document,
        organization_document,
        invisible_document,
    ]

    ProjectFactory(edit_collaborators=[edit_collaborator], edit_documents=documents)
    ProjectFactory(collaborators=[view_collaborator], edit_documents=documents)
    ProjectFactory(collaborators=[no_access_collaborator], documents=documents)

    for user, document, can_view, can_change, can_share in [
        (anonymous, public_document, True, False, False),
        (anonymous, public_pending_document, False, False, False),
        (anonymous, organization_document, False, False, False),
        (anonymous, private_document, False, False, False),
        (anonymous, invisible_document, False, False, False),
        (owner, public_document, True, True, True),
        (owner, public_pending_document, True, True, True),
        (owner, organization_document, True, True, True),
        (owner, private_document, True, True, True),
        (owner, invisible_document, False, False, False),
        (edit_collaborator, public_document, True, False, False),
        (edit_collaborator, public_pending_document, True, False, False),
        (edit_collaborator, organization_document, True, True, False),
        (edit_collaborator, private_document, True, True, False),
        (edit_collaborator, invisible_document, False, False, False),
        (view_collaborator, public_document, True, False, False),
        (view_collaborator, public_pending_document, True, False, False),
        (view_collaborator, organization_document, True, False, False),
        (view_collaborator, private_document, True, False, False),
        (view_collaborator, invisible_document, False, False, False),
        (no_access_collaborator, public_document, True, False, False),
        (no_access_collaborator, public_pending_document, False, False, False),
        (no_access_collaborator, organization_document, False, False, False),
        (no_access_collaborator, private_document, False, False, False),
        (no_access_collaborator, invisible_document, False, False, False),
        (organization_member, public_document, True, True, True),
        (organization_member, public_pending_document, True, True, True),
        (organization_member, organization_document, True, True, True),
        (organization_member, private_document, False, False, False),
        (organization_member, invisible_document, False, False, False),
    ]:
        assert (
            user.has_perm("documents.view_document", document) is can_view
        ), f"{user.get_full_name()} - {document.title}"
        assert (
            user.has_perm("documents.change_document", document) is can_change
        ), f"{user.get_full_name()} - {document.title}"
        assert (
            user.has_perm("documents.share_document", document) is can_share
        ), f"{user.get_full_name()} - {document.title}"
        assert (
            user.has_perm("documents.delete_document", document) is can_share
        ), f"{user.get_full_name()} - {document.title}"


@pytest.mark.django_db()
def test_note_rules():
    anonymous = AnonymousUser()
    owner = UserFactory(name="owner")
    organization_member = UserFactory(name="org")
    edit_collaborator = UserFactory(name="edit")
    view_collaborator = UserFactory(name="view")

    organization = OrganizationFactory(members=[owner, organization_member])
    organization_member.organization = organization

    public_note = NoteFactory(
        user=owner, organization=organization, access=Access.public, title="public"
    )
    organization_note = NoteFactory(
        user=owner, organization=organization, access=Access.organization, title="org"
    )
    private_note = NoteFactory(
        user=owner, organization=organization, access=Access.private, title="private"
    )
    invisible_note = NoteFactory(
        user=owner,
        organization=organization,
        access=Access.invisible,
        title="invisible",
    )

    documents = [
        public_note.document,
        organization_note.document,
        private_note.document,
        invisible_note.document,
    ]

    ProjectFactory(edit_collaborators=[edit_collaborator], edit_documents=documents)
    ProjectFactory(collaborators=[view_collaborator], documents=documents)

    for user, note, can_view, can_change in [
        (anonymous, public_note, True, False),
        (anonymous, organization_note, False, False),
        (anonymous, private_note, False, False),
        (anonymous, invisible_note, False, False),
        (owner, public_note, True, True),
        (owner, organization_note, True, True),
        (owner, private_note, True, True),
        (owner, invisible_note, False, False),
        (organization_member, public_note, True, False),
        (organization_member, organization_note, False, False),
        (organization_member, private_note, False, False),
        (organization_member, invisible_note, False, False),
        (edit_collaborator, public_note, True, False),
        (edit_collaborator, organization_note, False, False),
        (edit_collaborator, private_note, False, False),
        (edit_collaborator, invisible_note, False, False),
        (view_collaborator, public_note, True, False),
        (view_collaborator, organization_note, False, False),
        (view_collaborator, private_note, False, False),
        (view_collaborator, invisible_note, False, False),
    ]:
        assert (
            user.has_perm("documents.view_note", note) is can_view
        ), f"{user.get_full_name()} - {note.title}"
        assert (
            user.has_perm("documents.change_note", note) is can_change
        ), f"{user.get_full_name()} - {note.title}"
        assert (
            user.has_perm("documents.delete_note", note) is can_change
        ), f"{user.get_full_name()} - {note.title}"
