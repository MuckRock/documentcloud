# Django
from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

# Standard Library
import csv
import ctypes
import json
import os
import time

# Third Party
import pytz
from dateutil.parser import parse
from listcrunch.listcrunch import uncrunch
from reversion.models import Revision
from smart_open import open as smart_open
from social_django.models import UserSocialAuth

# DocumentCloud
from documentcloud.common.environment import httpsub, storage
from documentcloud.documents.choices import Access, Status
from documentcloud.documents.models import Document, Entity, EntityDate, Note, Section
from documentcloud.documents.tasks import solr_index_dirty
from documentcloud.organizations.models import Membership, Organization, Plan
from documentcloud.projects.choices import CollaboratorAccess
from documentcloud.projects.models import Collaboration, Project, ProjectMembership
from documentcloud.users.models import User

BUCKET = os.environ["IMPORT_BUCKET"]
IMPORT_DIR = os.environ["IMPORT_DIR"]

# pylint: disable=too-many-locals


def parse_date(date_str):
    if not date_str:
        return None
    else:
        return parse(date_str).replace(tzinfo=pytz.UTC)


class Command(BaseCommand):
    """Import users and orgs from old DocumentCloud"""

    def add_arguments(self, parser):
        parser.add_argument("organization", type=int, help="Organization ID to import")
        parser.add_argument(
            "--allow_duplicate",
            action="store_true",
            help="Allow the organization ID to exist in the database",
        )
        parser.add_argument(
            "--dry_run", action="store_true", help="Do not commit to database"
        )

    def handle(self, *args, **kwargs):
        # pylint: disable=unused-argument
        org_id = kwargs["organization"]
        dry_run = kwargs["dry_run"]
        self.allow_duplicate = kwargs["allow_duplicate"]
        self.bucket_path = f"s3://{BUCKET}/{IMPORT_DIR}/organization-{org_id}/"
        # https://stackoverflow.com/a/54517228/2204914
        csv.field_size_limit(int(ctypes.c_ulong(-1).value // 2))

        self.run_import_lambda(org_id)
        with transaction.atomic():
            sid = transaction.savepoint()
            org = self.import_org()
            self.import_users(org)
            self.import_documents()
            self.import_notes()
            self.import_sections()
            self.import_entities()
            self.import_entity_dates()
            self.import_projects()
            self.import_collaborations()
            self.import_project_memberships()

            if dry_run:
                self.stdout.write("Dry run, not commiting changes")
                transaction.savepoint_rollback(sid)

    def run_import_lambda(self, org_id):
        """Run the pre-process lambda script to generate the .txt.json files
        and to calculate the page spec for all documents
        """
        self.stdout.write("Begin Pre-Process Lambda {}".format(timezone.now()))
        httpsub.post(settings.IMPORT_URL, json={"org_id": org_id})
        # now we wait for the import script to finish by polling S3 for the existance
        # of the pagespec csv
        exists = False
        # strip off the s3://
        pagespec_path = f"{self.bucket_path}documents.pagespec.csv"[len("s3://") :]
        while not exists:
            self.stdout.write(
                "Waiting for pagespec CSV... {} {}".format(
                    pagespec_path, timezone.now()
                )
            )
            exists = storage.exists(pagespec_path)
            time.sleep(5)
        self.stdout.write("End Pre-Process Lambda {}".format(timezone.now()))

    def import_org(self):
        self.stdout.write("Begin Organization Import {}".format(timezone.now()))
        plan = Plan.objects.get(slug="free")

        # get the UUID from the map file
        with smart_open(f"{self.bucket_path}organizations_map.csv", "r") as mapfile:
            org_id, org_uuid = mapfile.read().strip().split(",")

        with smart_open(f"{self.bucket_path}organizations.csv", "r") as infile:
            reader = csv.reader(infile)
            next(reader)  # discard headers
            fields = next(reader)

            assert fields[0] == org_id

            org = Organization.objects.filter(uuid=org_uuid).first()
            if org:
                self.stdout.write(f"Updating {fields[1]}")
                if self.allow_duplicate:
                    assert (
                        org.pk == org_id
                        or not Organization.objects.filter(id=org_id).exists()
                    )
                else:
                    assert not Organization.objects.filter(id=org_id).exists()
                old_id = org.pk
                new_id = org_id
                # update the org's pk, and
                # language fields since they are not stored on squarelet
                Organization.objects.filter(id=old_id).update(
                    id=new_id, language=fields[6], document_language=fields[7]
                )
                # update all FKs pointing to the org
                Document.objects.filter(organization_id=old_id, solr_dirty=True).update(
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

    def import_users(self, org):
        self.stdout.write("Begin Users Import {}".format(timezone.now()))
        plan = Plan.objects.get(slug="free")

        with smart_open(f"{self.bucket_path}users.csv", "r") as infile, smart_open(
            f"{self.bucket_path}users_map.csv", "r"
        ) as mapfile:
            reader = csv.reader(infile)
            next(reader)  # discard headers
            map_reader = csv.reader(mapfile)

            create_users = []
            create_memberships = []

            for fields, (user_id, uuid, username, ind_org_slug) in zip(
                reader, map_reader
            ):
                # fields[0] is the user_id, it should match between files
                assert fields[0] == user_id, f"{fields[0]} != {user_id}"
                # 10 is role, 3 is reviewer - reveiwers should not be exported
                assert fields[10] != "3", f"Found a rogue reviewer, {user_id}"
                user = User.objects.filter(uuid=uuid).first()
                if user:
                    self.stdout.write(f"Updating {fields[3]}")
                    assert not User.objects.filter(id=user_id).exists()
                    old_id = user.pk
                    new_id = user_id
                    # update the user's pk, and
                    # language fields since they are not stored on squarelet
                    User.objects.filter(id=old_id).update(
                        id=new_id, language=fields[7], document_language=fields[8]
                    )
                    # update all FKs pointing to the user
                    Document.objects.filter(user_id=old_id).update(
                        user_id=new_id, solr_dirty=True
                    )
                    Note.objects.filter(user_id=old_id).update(user_id=new_id)
                    Membership.objects.filter(user_id=old_id).update(user_id=new_id)
                    Project.objects.filter(user_id=old_id).update(user_id=new_id)
                    Collaboration.objects.filter(user_id=old_id).update(user_id=new_id)
                    Collaboration.objects.filter(creator_id=old_id).update(
                        creator_id=new_id
                    )
                    Revision.objects.filter(user_id=old_id).update(user_id=new_id)
                    UserSocialAuth.objects.filter(user_id=old_id).update(user_id=new_id)
                    LogEntry.objects.filter(user_id=old_id).update(user_id=new_id)
                    # groups, permissions - pain to update, dont use them, punt for now
                    user = User.objects.get(pk=new_id)
                    if fields[10] not in ("0", "4") and not org.has_member(user):
                        create_memberships.append(
                            Membership(
                                user=user,
                                organization=org,
                                active=False,
                                admin=fields[10] == "1",
                            )
                        )
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
                            created_at=parse_date(fields[5]),
                            updated_at=parse_date(fields[6]),
                            language=fields[7],
                            document_language=fields[8],
                        )
                    )
                    individual_organization = Organization.objects.create(
                        uuid=uuid,
                        name=username,
                        slug=ind_org_slug,
                        private=True,
                        individual=True,
                        plan=plan,
                        verified_journalist=False,
                        language=fields[7],
                        document_language=fields[8],
                    )
                    if fields[10] not in ("0", "4"):
                        create_memberships.append(
                            Membership(
                                user_id=user_id,
                                organization=org,
                                active=True,
                                admin=fields[10] == "1",
                            )
                        )
                        create_memberships.append(
                            Membership(
                                user_id=user_id,
                                organization=individual_organization,
                                active=False,
                                admin=True,
                            )
                        )
                    else:
                        create_memberships.append(
                            Membership(
                                user_id=user_id,
                                organization=individual_organization,
                                active=True,
                                admin=True,
                            )
                        )

            User.objects.bulk_create(create_users)
            Membership.objects.bulk_create(create_memberships)

        self.stdout.write("End Organization Import {}".format(timezone.now()))

    def import_documents(self):
        self.stdout.write("Begin Documents Import {}".format(timezone.now()))

        access_status_map = {
            # DELETED
            "0": (Access.invisible, Status.deleted),
            # PRIVATE
            "1": (Access.private, Status.success),
            # ORGANIZATION
            "2": (Access.organization, Status.success),
            # EXCLUSIVE
            "3": (Access.organization, Status.success),
            # PUBLIC
            "4": (Access.public, Status.success),
            # PENDING
            "5": (Access.private, Status.pending),
            # INVISIBLE
            "6": (Access.invisible, Status.success),
            # ERROR
            "7": (Access.private, Status.error),
            # PREMODERATED
            "8": (Access.public, Status.success),
            # POSTMODERATED
            "9": (Access.public, Status.success),
        }

        with smart_open(f"{self.bucket_path}documents.pagespec.csv", "r") as infile:
            reader = csv.reader(infile)
            next(reader)  # discard headers

            create_docs = []

            for i, fields in enumerate(reader):
                if i % 10000 == 0:
                    self.stdout.write(f"Document {i:,}...")
                # assert fields[0] == doc_id
                access, status = access_status_map[fields[3]]
                if fields[26]:
                    # wrap the data dictionary so each value is in a list now
                    data = {k: [v] for k, v in json.loads(fields[26]).items()}
                else:
                    data = {}
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
                        page_spec=fields[27],
                        language=fields[8],
                        source=fields[7],
                        description=fields[9],
                        created_at=parse_date(fields[12]),
                        updated_at=parse_date(fields[13]),
                        solr_dirty=True,
                        data=data,
                        related_article=fields[14],
                        published_url=fields[16],
                        detected_remote_url=fields[15],
                        file_hash=fields[25],
                        calais_id=fields[10],
                        publication_date=parse_date(fields[11]),
                        publish_at=parse_date(fields[17]),
                        text_changed=fields[18] == "t",
                        hit_count=fields[19],
                        public_note_count=fields[20],
                        file_size=fields[21],
                        char_count=fields[23],
                        original_extension=fields[24],
                    )
                )
                if i % 1000 == 999:
                    Document.objects.bulk_create(create_docs, batch_size=1000)
                    del create_docs
                    create_docs = []

            Document.objects.bulk_create(create_docs, batch_size=1000)

        # start indexing the documents on commit
        transaction.on_commit(solr_index_dirty.delay)

        self.stdout.write("End Documents Import {}".format(timezone.now()))

    def import_notes(self):
        self.stdout.write("Begin Notes Import {}".format(timezone.now()))

        access_map = {
            # DELETED
            "0": Access.private,
            # PRIVATE
            "1": Access.private,
            # ORGANIZATION
            "2": Access.organization,
            # EXCLUSIVE
            "3": Access.organization,
            # PUBLIC
            "4": Access.public,
            # PENDING
            "5": Access.private,
            # INVISIBLE
            "6": Access.invisible,
            # ERROR
            "7": Access.private,
            # PREMODERATED
            "8": Access.public,
            # POSTMODERATED
            "9": Access.public,
        }

        with smart_open(f"{self.bucket_path}notes.csv", "r") as infile:
            reader = csv.reader(infile)
            next(reader)  # discard headers

            create_notes = []
            document_ids = []

            for fields in reader:
                if fields[8]:  # 8 is location
                    y1, x2, y2, x1 = [int(i) for i in fields[8].split(",")]
                    # add document_id to list of documents to load
                    document_ids.append(fields[3])
                else:
                    x1 = x2 = y1 = y2 = None
                create_notes.append(
                    Note(
                        id=fields[0],
                        document_id=fields[3],
                        user_id=fields[2],
                        organization_id=fields[1],
                        page_number=int(fields[4]) - 1,
                        access=access_map[fields[5]],
                        title=fields[6],
                        content=fields[7],
                        x1=x1,
                        x2=x2,
                        y1=y1,
                        y2=y2,
                        created_at=parse_date(fields[9]),
                        updated_at=parse_date(fields[10]),
                    )
                )

            # create a dictionary mapping document ids to
            # the uncrunched page specs
            page_specs = Document.objects.filter(pk__in=document_ids).values_list(
                "pk", "page_spec"
            )
            document_map = {
                str(pk): uncrunch(page_spec)
                for pk, page_spec in page_specs
                if page_spec
            }

            for note in create_notes:
                # if the note has coordinates and the document is in the map then
                # grab the coordinates of the correct page and convert
                # all the coordinates to percentages
                if note.x1 is not None and note.document_id in document_map:
                    width, height = map(
                        float,
                        document_map[note.document_id][note.page_number].split("x"),
                    )
                    # normalize to a width of 700
                    height = (700 / width) * height
                    width = 700
                    note.x1 /= width
                    note.x2 /= width
                    note.y1 /= height
                    note.y2 /= height
                elif note.x1 is not None and note.document_id not in document_map:
                    # if we do not have page specs, guess!
                    # all pages should have a width of 700, and we will use
                    # a standard height of 906
                    # this will happen if it is a private note on a document
                    # that has not been imported yet
                    note.x1 /= 700.0
                    note.x2 /= 700.0
                    note.y1 /= 906.0
                    note.y2 /= 906.0
                    # if we guessed the height wrong just reduce it
                    if note.y1 > 1:
                        self.stdout.write(f"y1 was outside bounds, setting to 0.9")
                        note.y1 = 0.9
                    if note.y2 > 1:
                        self.stdout.write(f"y2 was outside bounds, setting to 1.0")
                        note.y2 = 1.0

            Note.objects.bulk_create(create_notes, batch_size=1000)

        self.stdout.write("End Notes Import {}".format(timezone.now()))

    def import_sections(self):
        self.stdout.write("Begin Sections Import {}".format(timezone.now()))

        with smart_open(f"{self.bucket_path}sections.csv", "r") as infile:
            reader = csv.reader(infile)
            next(reader)  # discard headers

            create_sections = []

            for fields in reader:
                create_sections.append(
                    Section(
                        document_id=fields[3],
                        page_number=fields[6] - 1,
                        title=fields[5],
                    )
                )

            Section.objects.bulk_create(create_sections, batch_size=1000)

        self.stdout.write("End Sections Import {}".format(timezone.now()))

    def import_entities(self):
        self.stdout.write("Begin Entities Import {}".format(timezone.now()))

        with smart_open(f"{self.bucket_path}entities.csv", "r") as infile:
            reader = csv.reader(infile)
            next(reader)  # discard headers

            create_entities = []

            for i, fields in enumerate(reader):
                if i % 100000 == 0:
                    self.stdout.write(f"Entity {i:,}...")
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
                if i % 1000 == 999:
                    Entity.objects.bulk_create(create_entities, batch_size=1000)
                    del create_entities
                    create_entities = []

            Entity.objects.bulk_create(create_entities, batch_size=1000)

        self.stdout.write("End Entities Import {}".format(timezone.now()))

    def import_entity_dates(self):
        self.stdout.write("Begin Entity Dates Import {}".format(timezone.now()))

        with smart_open(f"{self.bucket_path}entity_dates.csv", "r") as infile:
            reader = csv.reader(infile)
            next(reader)  # discard headers

            create_entities = []

            for i, fields in enumerate(reader):
                if i % 100000 == 0:
                    self.stdout.write(f"Entity date {i:,}...")
                create_entities.append(
                    EntityDate(
                        document_id=fields[3],
                        date=parse_date(fields[5]),
                        occurrences=fields[6],
                    )
                )
                if i % 1000 == 999:
                    EntityDate.objects.bulk_create(create_entities, batch_size=1000)
                    del create_entities
                    create_entities = []

            EntityDate.objects.bulk_create(create_entities, batch_size=1000)

        self.stdout.write("End Entity Dates Import {}".format(timezone.now()))

    def import_projects(self):
        self.stdout.write("Begin Projects Import {}".format(timezone.now()))

        with smart_open(f"{self.bucket_path}projects.csv", "r") as infile:
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

        with smart_open(f"{self.bucket_path}collaborations.csv", "r") as infile:
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

            # old doc cloud did not enforce unique constraints on (project_id, user_id)
            # we will ignore these conflicts
            Collaboration.objects.bulk_create(
                create_collabs, batch_size=1000, ignore_conflicts=True
            )

        self.stdout.write("End Collaborations Import {}".format(timezone.now()))

    def import_project_memberships(self):
        self.stdout.write("Begin Project Memberships Import {}".format(timezone.now()))

        with smart_open(f"{self.bucket_path}project_memberships.csv", "r") as infile:
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
