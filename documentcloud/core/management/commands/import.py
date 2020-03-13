# Django
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

# Standard Library
import csv
import json
import os

# Third Party
from dateutil.parser import parse
from listcrunch.listcrunch import uncrunch
from smart_open.smart_open_lib import smart_open

# DocumentCloud
from documentcloud.documents.choices import Access, Status
from documentcloud.documents.models import Document, Entity, EntityDate, Note, Section
from documentcloud.documents.tasks import solr_index_dirty
from documentcloud.organizations.models import Membership, Organization, Plan
from documentcloud.projects.choices import CollaboratorAccess
from documentcloud.projects.models import Collaboration, Project, ProjectMembership
from documentcloud.users.models import User

BUCKET = os.environ["IMPORT_BUCKET"]


class Command(BaseCommand):
    """Import users and orgs from old DocumentCloud"""

    def add_arguments(self, parser):
        parser.add_argument("organization", type=int, help="Organization ID to import")

    def handle(self, *args, **kwargs):
        # pylint: disable=unused-argument
        org_id = kwargs["organization"]
        self.bucket_path = f"s3://{BUCKET}/documentcloud-export/organization-{org_id}/"
        with transaction.atomic():
            self.import_org()
            self.import_users()
            self.import_documents()
            self.import_notes()
            self.import_sections()
            self.import_entities()
            self.import_entity_dates()
            self.import_projects()
            self.import_collaborations()
            self.import_project_memberships()

    def import_org(self):
        self.stdout.write("Begin Organization Import {}".format(timezone.now()))
        plan = Plan.objects.get(slug="free")

        # get the UUID from the map file
        with smart_open(f"{self.bucket_path}organizations_map.csv", "rb") as mapfile:
            org_id, org_uuid = mapfile.read().strip().split(",")

        with smart_open(f"{self.bucket_path}organizations.csv", "rb") as infile:
            reader = csv.reader(infile)
            next(reader)  # discard headers
            fields = next(reader)

            assert fields[0] == org_id

            org = Organization.objects.filter(uuid=org_uuid).first()
            if org:
                # XXX test this
                self.stdout.write(f"Updating {fields[1]}")
                assert not Organization.objects.filter(id=org_id).exists()
                old_id = org.pk
                new_id = org_id
                # update the org's pk, and
                # language fields since they are not stored on squarelet
                Organization.objects.filter(id=old_id).update(
                    id=new_id, language=fields[6], document_language=fields[7]
                )
                # update all FKs pointing to the org
                Document.objects.filter(organization_id=old_id).update(
                    organization_id=new_id
                )
                Note.objects.filter(organization_id=old_id).update(
                    organization_id=new_id
                )
                Membership.objects.filter(organization_id=old_id).update(
                    organization_id=new_id
                )
                org = Organization.objects.get(pk=new_id)
            else:
                self.stdout.write(f"Creating {fields[1]}")
                org = Organization.objects.create(
                    id=fields[0],
                    uuid=org_uuid,
                    name=fields[1],
                    slug=fields[2],
                    private=fields[9] == "t",
                    individual=False,
                    plan=plan,
                    verified_journalist=True,
                    language=fields[6],
                    document_language=fields[7],
                )
        self.stdout.write("End Organization Import {}".format(timezone.now()))
        return org

    def import_users(self):
        self.stdout.write("Begin Users Import {}".format(timezone.now()))

        with smart_open(f"{self.bucket_path}users.csv", "rb") as infile, smart_open(
            f"{self.bucket_path}users_map.csv", "rb"
        ) as mapfile:
            reader = csv.reader(infile)
            next(reader)  # discard headers
            map_reader = csv.reader(mapfile)

            create_users = []

            for fields, (user_id, uuid, username) in zip(reader, map_reader):
                assert fields[0] == user_id
                user = User.objects.filter(uuid=uuid).first()
                if user:
                    self.stdout.write(f"Updating {fields[3]}")
                    assert not User.objects.filter(id=user_id).exists()
                    old_id = user.pk
                    new_id = user_id
                    # update the user's pk, and
                    # language fields since they are not stored on squarelet
                    Organization.objects.filter(id=old_id).update(
                        id=new_id, language=fields[7], document_language=fields[8]
                    )
                    # update all FKs pointing to the user
                    Document.objects.filter(user_id=old_id).update(user_id=new_id)
                    Note.objects.filter(user_id=old_id).update(user_id=new_id)
                    Membership.objects.filter(user_id=old_id).update(user_id=new_id)
                    Project.objects.filter(user_id=old_id).update(user_id=new_id)
                    Collaboration.objects.filter(user_id=old_id).update(user_id=new_id)
                    Collaboration.objects.filter(creator_id=old_id).update(
                        creator_id=new_id
                    )
                    user = User.objects.get(pk=new_id)
                else:
                    self.stdout.write(f"Creating {fields[3]}")
                    create_users.append(
                        User(
                            id=user_id,
                            uuid=uuid,
                            name=f"{fields[1]} {fields[2]}",
                            email=fields[3],
                            username=username,
                            email_verified=True,
                            created_at=parse(fields[5]),
                            updated_at=parse(fields[6]),
                            language=fields[7],
                            document_language=fields[8],
                        )
                    )

            User.objects.bulk_create(create_users)

        self.stdout.write("End Organization Import {}".format(timezone.now()))

    def import_documents(self):
        self.stdout.write("Begin Documents Import {}".format(timezone.now()))

        access_status_map = {
            # DELETED
            0: (Access.invisible, Status.deleted),
            # PRIVATE
            1: (Access.private, Status.success),
            # ORGANIZATION
            2: (Access.organization, Status.success),
            # EXCLUSIVE
            3: (Access.organization, Status.success),
            # PUBLIC
            4: (Access.public, Status.success),
            # PENDING
            5: (Access.private, Status.pending),
            # INVISIBLE
            6: (Access.invisible, Status.success),
            # ERROR
            7: (Access.private, Status.error),
            # PREMODERATED
            8: (Access.public, Status.success),
            # POSTMODERATED
            9: (Access.public, Status.success),
        }

        with smart_open(f"{self.bucket_path}documents.csv", "rb") as infile, smart_open(
            f"{self.bucket_path}documents_pagespecs.csv", "rb"
        ) as psfile:
            reader = csv.reader(infile)
            next(reader)  # discard headers
            ps_reader = csv.reader(psfile)

            create_docs = []

            for fields in reader:
            for fields, (doc_id, page_spec) in zip(reader, ps_reader):
                assert fields[0] == doc_id
                access, status = access_status_map[fields[3]]
                create_docs.append(
                    Document(
                        id=fields[0],
                        user_id=fields[2],
                        organization_id=fields[1],
                        access=access,
                        status=status,
                        title=fields[5],
                        slug=fields[6],
                        page_count=fields[4],
                        page_spec=page_spec,
                        language=fields[8],
                        source=fields[7],
                        description=fields[9],
                        created_at=parse(fields[12]),
                        updated_at=parse(fields[13]),
                        solr_dirty=True,
                        data=json.loads(fields[26]) if fields[26] else {},
                        related_article=fields[14],
                        remote_url=fields[16],
                        detected_remote_url=fields[15],
                        file_hash=fields[25],
                        calais_id=fields[10],
                        publication_date=parse(fields[11]),
                        publish_at=parse(fields[17]),
                        text_changed=fields[18] == "t",
                        hit_count=fields[19],
                        public_note_count=fields[20],
                        file_size=fields[21],
                        char_count=fields[23],
                        original_extension=fields[24],
                    )
                )

            Document.objects.bulk_create(create_docs, batch_size=1000)

        # start indexing the documents
        solr_index_dirty.delay()

        self.stdout.write("End Documents Import {}".format(timezone.now()))

    def import_notes(self):
        self.stdout.write("Begin Notes Import {}".format(timezone.now()))

        access_map = {
            # PRIVATE
            1: Access.private,
            # ORGANIZATION
            2: Access.organization,
            # EXCLUSIVE
            3: Access.organization,
            # PUBLIC
            4: Access.public,
            # INVISIBLE
            6: Access.invisible,
            # PREMODERATED
            8: Access.public,
            # POSTMODERATED
            9: Access.public,
        }

        with smart_open(f"{self.bucket_path}notes.csv", "rb") as infile:
            reader = csv.reader(infile)
            next(reader)  # discard headers

            create_notes = []
            document_ids = []

            for fields in reader:
                if fields[8]:  # 8 is location
                    y1, x2, y2, x1 = fields[8].split(",")
                    # add document_id to lift of documents to load
                    document_ids.append(fields[3])
                else:
                    x1 = x2 = y1 = y2 = None
                create_notes.append(
                    Note(
                        id=fields[0],
                        document_id=fields[3],
                        user_id=fields[2],
                        organization_id=fields[1],
                        page_number=fields[4],
                        access=access_map.get(fields[5], Access.private),
                        title=fields[6],
                        content=fields[7],
                        x1=x1,
                        x2=x2,
                        y1=y1,
                        y2=y2,
                        created_at=fields[9],
                        updated_at=fields[10],
                    )
                )

            # create a dictionary mapping document ids to
            # the uncrunched page specs
            document_map = {
                pk: uncrunch(page_spec)
                for pk, page_spec in Document.objects.filter(
                    pk__in=document_ids
                ).values_list("pk", "page_spec")
                if page_spec
            }

            for note in create_notes:
                # if the note has coordinates and the document is in the map then
                # grab the coordinates of the correct page and convert
                # all the coordinates to percentages
                if note.x1 is not None and note.document_id in document_map:
                    width, height = document_map[note.document_id][
                        note.page_number
                    ].split("x")
                    note.x1 /= width
                    note.x2 /= width
                    note.y1 /= height
                    note.y2 /= height
                elif note.x1 is not None and note.document_id not in document_map:
                    # XXX if we do not have page specs make it a page level note
                    # this will happen if it is a private note on a document
                    # that has not been imported yet
                    # XXX allow for note moving?
                    note.x1 = None
                    note.x2 = None
                    note.y1 = None
                    note.y2 = None

            Note.objects.bulk_create(create_notes, batch_size=1000)

        self.stdout.write("End Notes Import {}".format(timezone.now()))

    def import_sections(self):
        self.stdout.write("Begin Sections Import {}".format(timezone.now()))

        with smart_open(f"{self.bucket_path}sections.csv", "rb") as infile:
            reader = csv.reader(infile)
            next(reader)  # discard headers

            create_sections = []

            for fields in reader:
                create_sections.append(
                    Section(
                        document_id=fields[3], page_number=fields[6], title=fields[5]
                    )
                )

            Section.objects.bulk_create(create_sections, batch_size=1000)

        self.stdout.write("End Sections Import {}".format(timezone.now()))

    def import_entities(self):
        self.stdout.write("Begin Entities Import {}".format(timezone.now()))

        with smart_open(f"{self.bucket_path}entities.csv", "rb") as infile:
            reader = csv.reader(infile)
            next(reader)  # discard headers

            create_entities = []

            for fields in reader:
                create_entities.append(
                    Entity(
                        document_id=fields[3],
                        kind=fields[5],
                        value=fields[6],
                        relevance=fields[7],
                        calais_id=fields[8],
                        occurrences=fields[9],
                    )
                )

            Entity.objects.bulk_create(create_entities, batch_size=1000)

        self.stdout.write("End Entities Import {}".format(timezone.now()))

    def import_entity_dates(self):
        self.stdout.write("Begin Entity Dates Import {}".format(timezone.now()))

        with smart_open(f"{self.bucket_path}entity_dates.csv", "rb") as infile:
            reader = csv.reader(infile)
            next(reader)  # discard headers

            create_entities = []

            for fields in reader:
                create_entities.append(
                    EntityDate(
                        document_id=fields[3],
                        date=parse(fields[5]),
                        occurrences=fields[6],
                    )
                )

            EntityDate.objects.bulk_create(create_entities, batch_size=1000)

        self.stdout.write("End Entity Dates Import {}".format(timezone.now()))

    def import_projects(self):
        self.stdout.write("Begin Projects Import {}".format(timezone.now()))

        with smart_open(f"{self.bucket_path}projects.csv", "rb") as infile:
            reader = csv.reader(infile)
            next(reader)  # discard headers

            create_projects = []

            for fields in reader:
                create_projects.append(
                    Project(
                        id=fields[0],
                        user_id=fields[1],
                        title=fields[2],
                        description=fields[3],
                    )
                )

            # we ignore_conflicts as we may have already imported the project
            # in that case we are safe to do nothing
            Project.objects.bulk_create(
                create_projects, batch_size=1000, ignore_conflicts=True
            )

        self.stdout.write("End Entity Dates Import {}".format(timezone.now()))

    def import_collaborations(self):
        self.stdout.write("Begin Collaborations Import {}".format(timezone.now()))

        with smart_open(f"{self.bucket_path}collaborations.csv", "rb") as infile:
            reader = csv.reader(infile)
            next(reader)  # discard headers

            create_collabs = []

            for fields in reader:
                create_collabs.append(
                    Collaboration(
                        project_id=fields[0],
                        user_id=fields[1],
                        creator_id=fields[2],
                        access=CollaboratorAccess.edit,
                    )
                )

            Collaboration.objects.bulk_create(create_collabs, batch_size=1000)

        self.stdout.write("End Collaborations Import {}".format(timezone.now()))

    def import_project_memberships(self):
        self.stdout.write("Begin Project Memberships Import {}".format(timezone.now()))

        with smart_open(f"{self.bucket_path}project_memberships.csv", "rb") as infile:
            reader = csv.reader(infile)
            next(reader)  # discard headers

            create_pms = []

            for fields in reader:
                create_pms.append(
                    ProjectMembership(
                        project_id=fields[0],
                        document_id=fields[1],
                        edit_access=fields[2] == "t",
                    )
                )

            ProjectMembership.objects.bulk_create(create_pms, batch_size=1000)

        self.stdout.write("End Project Memberships Import {}".format(timezone.now()))
