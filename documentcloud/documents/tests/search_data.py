# Standard Library
from datetime import datetime

# Third Party
import pytz

# DocumentCloud
from documentcloud.documents.choices import Access, Status

ORGANIZATIONS = [
    {"id": 1, "name": "The Daily Planet", "entitlement": "org"},
    {"id": 2, "name": "The Daily Bugle", "entitlement": "org"},
    {"id": 3, "name": "The Daily Prophet"},
]


USERS = [
    {"id": 1, "name": "Clark Kent", "organization": 1},
    {"id": 2, "name": "Lois Lane", "organization": 1},
    {"id": 3, "name": "Peter Parker", "organization": 2},
    {"id": 4, "name": "Eddie Brock", "organization": 2},
    {"id": 5, "name": "Barnabas Cuffe", "organization": 3},
    {"id": 6, "name": "Ginevra Weasley", "organization": 3},
    {"id": 7, "name": "Mary Jane Watson", "organization": 2},
]


DOCUMENTS = [
    {
        "id": 1,
        "user": 1,
        "organization": 1,
        "title": "Superman Letter",
        "source": "Lex Luther",
        "description": "A friendly note",
        "access": Access.public,
        "status": Status.success,
        "created_at": datetime(2011, 1, 1, tzinfo=pytz.utc),
    },
    {
        "id": 2,
        "user": 1,
        "organization": 1,
        "title": "Metropolis Contract",
        "description": "Not a letter",
        "access": Access.public,
        "status": Status.success,
        "created_at": datetime(2011, 2, 1, tzinfo=pytz.utc),
    },
    {
        "id": 3,
        "user": 1,
        "organization": 1,
        "title": "Superman Review",
        "access": Access.private,
        "status": Status.success,
        "created_at": datetime(2011, 2, 2, tzinfo=pytz.utc),
    },
    {
        "id": 4,
        "user": 2,
        "organization": 1,
        "title": "Superman Contract",
        "access": Access.public,
        "status": Status.success,
        "created_at": datetime(2011, 3, 1, tzinfo=pytz.utc),
    },
    {
        "id": 5,
        "user": 2,
        "organization": 1,
        "title": "Metropolis Form",
        "access": Access.public,
        "status": Status.success,
        "created_at": datetime(2011, 4, 1, tzinfo=pytz.utc),
    },
    {
        "id": 6,
        "user": 2,
        "organization": 1,
        "title": "Supergirl Contract",
        "access": Access.organization,
        "status": Status.success,
        "created_at": datetime(2011, 4, 2, tzinfo=pytz.utc),
    },
    {
        "id": 7,
        "user": 3,
        "organization": 2,
        "title": "Spiderman Form",
        "access": Access.public,
        "status": Status.readable,
        "created_at": datetime(2011, 5, 1, tzinfo=pytz.utc),
    },
    {
        "id": 8,
        "user": 3,
        "organization": 2,
        "title": "New York Letter",
        "access": Access.public,
        "status": Status.success,
        "created_at": datetime(2011, 6, 1, tzinfo=pytz.utc),
        "data": {"edition": "first"},
    },
    {
        "id": 9,
        "user": 3,
        "organization": 2,
        "title": "Green Goblin Notes",
        "access": Access.invisible,
        "status": Status.success,
        "created_at": datetime(2011, 6, 2, tzinfo=pytz.utc),
    },
    {
        "id": 10,
        "user": 4,
        "organization": 2,
        "title": "Spiderman Contract",
        "access": Access.public,
        "status": Status.success,
        "created_at": datetime(2011, 7, 1, tzinfo=pytz.utc),
        "data": {"edition": "second"},
    },
    {
        "id": 11,
        "user": 4,
        "organization": 2,
        "title": "New York Form",
        "access": Access.public,
        "status": Status.error,
        "created_at": datetime(2011, 8, 1, tzinfo=pytz.utc),
    },
    {
        "id": 12,
        "user": 5,
        "organization": 3,
        "title": "Harry Potter Info",
        "access": Access.public,
        "status": Status.success,
        "created_at": datetime(2011, 9, 1, tzinfo=pytz.utc),
    },
    {
        "id": 13,
        "user": 5,
        "organization": 3,
        "title": "Quidditch Scores",
        "access": Access.public,
        "status": Status.success,
        "created_at": datetime(2011, 10, 1, tzinfo=pytz.utc),
    },
    {
        "id": 14,
        "user": 6,
        "organization": 3,
        "title": "Harry Potter Letter",
        "access": Access.public,
        "status": Status.success,
        "created_at": datetime(2011, 11, 1, tzinfo=pytz.utc),
    },
    {
        "id": 15,
        "user": 6,
        "organization": 3,
        "title": "Quidditch Info",
        "access": Access.public,
        "status": Status.success,
        "created_at": datetime(2011, 12, 1, tzinfo=pytz.utc),
    },
    {
        "id": 16,
        "user": 6,
        "organization": 3,
        "title": "Harry Potter Form",
        "access": Access.invisible,
        "status": Status.success,
        "created_at": datetime(2011, 12, 1, tzinfo=pytz.utc),
    },
]


NOTES = [
    {
        "id": 1,
        "user": 2,
        "organization": 1,
        "document": 1,
        "page_number": 0,
        "content": "alice",
        "access": Access.public,
    },
    {
        "id": 2,
        "user": 2,
        "organization": 1,
        "document": 1,
        "page_number": 1,
        "content": "bob",
        "access": Access.private,
    },
    {
        "id": 3,
        "user": 2,
        "organization": 1,
        "document": 1,
        "page_number": 0,
        "content": "charlie",
        "access": Access.organization,
    },
    {
        "id": 4,
        "user": 1,
        "organization": 1,
        "document": 3,
        "page_number": 0,
        "content": "delta",
        "access": Access.public,
    },
    {
        "id": 5,
        "user": 1,
        "organization": 1,
        "document": 3,
        "page_number": 1,
        "content": "echo",
        "access": Access.private,
    },
    {
        "id": 6,
        "user": 1,
        "organization": 1,
        "document": 3,
        "page_number": 0,
        "content": "foxtrot",
        "access": Access.organization,
    },
]


PROJECTS = [
    {
        "id": 1,
        "user": 1,
        "title": "Superman Project",
        "documents": [1, 3],
        "collaborators": [3],
        "edit_collaborators": [4, 7],
    }
]
