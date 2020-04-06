
# The DocumentCloud API

All APIs besides the authentication endpoints are served from
<https://api.beta.documentcloud.org/api>.

## Contents

* [Overview](#overview)
* [Authentication](#authentication)
* [Documents](#documents)
    * [Notes](#notes)
    * [Sections](#sections)
    <!-- No entity support yet
    * [Entities](#entities)
    * [Entity Dates](#entity-dates)
    -->
    * [Errors](#errors)
    * [Data](#data)
    * [Redactions](#redactions)
* [Projects](#projects)
    * [Documents](#project-documents)
    * [Collaborators](#collaborators)
* [Organizations](#organizations)
* [Users](#users)
* [oEmbed](#oembed)
* [Appendix](#appendix)
    * [Access Levels](#access-levels)
    * [Statuses](#statuses)
    * [Languages](#languages)
    * [Page Spec](#page-spec)
    * [Static Assets](#static-assets)

## Overview

The API end points are generally organized as `/api/<resource>/` representing
the entirety of the resource, and `/api/<resource>/<id>/` representing a single
resource identified by its ID.  All REST actions are not available on every
endpoint, and some resources may have additional endpoints, but the following
are how HTTP verbs generally map to REST operations:

`/api/<resource>/`

| HTTP Verb | REST Operation        | Parameters                                                                   |
| ---       | ---                   | ---                                                                          |
| GET       | List the resources    | May support parameters for filtering                                         |
| POST      | Create a new resource | Must supply all `required` fields, and may supply all non-`read only` fields |

`/api/<resource>/<id>/`

| HTTP Verb | REST Operation                | Parameters                                                                                                                                                                                                       |
| ---       | ---                           | ---                                                                                                                                                                                                              |
| GET       | Display the resource          |                                                                                                                                                                                                                  |
| PUT       | Update the resource           | Same as for creating - all required fields must be present.  For updating resources `PATCH` is usually preferred, as it allows you to only update the fields needed.  `PUT` support is included for completeness |
| PATCH     | Partially update the resource | Same as for creating, but all fields are optional                                                                                                                                                                |
| DELETE    | Destroy the resources         |                                                                                                                                                                                                                  |

A select few of the resources support some bulk operations on the `/api/<resource>/` route:

| HTTP Verb | REST Operation      | Parameters                                                                                                                    |
| ---       | ---                 | ---                                                                                                                           |
| PUT       | Bulk update         | A list of objects, where each object is what you would `PUT` for a single object &mdash; except it must also include the ID   |
| PATCH     | Bulk partial update | A list of objects, where each object is what you would `PATCH` for a single object &mdash; except it must also include the ID |
| DELETE    | Bulk destroy        | Bulk destroys will have a filtering parameter, often required, to specify which resources to delete                           |

### Responses

Lists response will be of the form
```
{
    "count": <count>,
    "next": <next url if applicable>,
    "previous": <previous url if applicable>,
    "results": <list of results>
}
```
with a 200 status code.

Getting a single resource, creating and updating will return just the object.
Create uses a 201 status code and get and update will return 200.

Delete will have an empty response with a 204 status code.

Batch updates will contain a list of objects updated with a 200 status code.

Specifying invalid parameters will generally return a 400 error code with a
JSON object with a single `"error"` key, whose value will be an error message.
Specifying an ID that does not exist or that you do not have access to view
will return status 404.  Trying to create or update a resource you do not have
permission to will return status 403.

### Pagination

All list views accept a `per_page` parameter, which specifies how many
resources to list per page.  It is `25` by default and may be set up to `1000`.
You may view subsequent pages by using the `next` URL, or by specifying a
`page` parameter directly.

### Sub Resources

Some resources also support sub resources, which is a resource that belongs to another.  The general format is:

`/api/<resource>/<id>/<subresource>/`

or

`/api/<resource>/<id>/<subresource>/<subresource_id>/`

It generally works the same as a resource, except scoped to the parent resource.

TODO: Examples

### Filters

Filters on list views which have choices generally allow you to specify
multiple values, and will filter on all resources that match at least one
choices.  To specify multiple parameters you may either supply a comma
separated list of IDs &mdash; `?parameter=1,2` &mdash; or by specify the
parameter multiple times &mdash; `?parameter=1&parameter=2`.

## Authentication

Authentication happens at the MuckRock accounts server located at
<https://accounts.muckrock.com/>.  The API provided there will supply you with
a [JWT][1] access token and refresh token in exchange for your username and
password.  The access token should be placed in the `Authorization` header
preceded by `Bearer` - `{'Authorization': 'Bearer <access token>'}`.  The
access token is valid for 5 minutes, after which you will receive a 403
forbidden error if you continue trying to use it.  At this point you may use
the refresh token to obtain a new access token and refresh token.  The refresh
token is valid for one day.

### POST /api/token/
| Param    | Type   | Description   |
| ---      | ---    | --            |
| username | string | Your username |
| password | string | Your password |

#### Response
    {'access': <access token>, 'refresh': <refresh token>}

### POST /api/refresh/
| Param   | Type   | Description   |
| ---     | ---    | --            |
| refresh | string | Refresh token |

#### Response
    {'access': <access token>, 'refresh': <refresh token>}

## Documents

The documents API allows you to upload, browse and edit documents.  To add or
remove documents from a project, please see [project
documents](#project-documents).

### Fields

| Field            | Type         | Options            | Description                                                                                                                                                       |
| ---              | ---          | ---                | ---                                                                                                                                                               |
| ID               | Integer      | Read Only          | The ID for the document                                                                                                                                           |
| access           | String       | Default: `private` | The [access level](#access-levels) for the document                                                                                                               |
| asset\_url       | String       | Read Only          | The base URL to load this document's [static assets](#static-assets) from                                                                                         |
| created\_at      | Date Time    | Read Only          | Time stamp when this document was created                                                                                                                         |
| data             | JSON         | Not Required       | [Custom metadata](#data)                                                                                                                                          |
| description      | String       | Not Required       | A brief description of the document                                                                                                                               |
| edit\_access     | Bool         | Read Only          | Does the current user have edit access to this document                                                                                                           |
| file\_url        | URL          | Create Only        | A URL to a publicly accessible document for the [URL Upload Flow](#url-upload-flow)                                                                               |
| language         | String       | Default: `eng`     | The [language](#languages) the document is in                                                                                                                     |
| organization     | Integer      | Read Only          | The ID for the [organization](#organizations) this document belongs to                                                                                            |
| page\_count      | Integer      | Read Only          | The number of pages in this document                                                                                                                              |
| page\_spec       | Integer      | Read Only          | [The dimensions for all pages in the document](#page-spec)                                                                                                        |
| presigned\_url   | URL          | Read Only          | The pre-signed URL to [directly](#direct-file-upload-flow) `PUT` the PDF file to                                                                                  |
| projects         | List:Integer | Create Only        | The IDs of the [projects](#projects) this document belongs to - this may be set on creation, but may not be updated.  See [project documents](#project-documents) |
| related\_article | URL          | Not Required       | The URL for the article about this document                                                                                                                       |
| remaining        | JSON         | Read Only          | The number of pages left for text and image processing - only included if `remaining` is included as a `GET` parameter                                            |
| published\_url   | URL          | Not Required       | The URL where this document is embedded                                                                                                                           |
| slug             | String       | Read Only          | The slug is a URL safe version of the title                                                                                                                       |
| source           | String       | Not Required       | The source who produced the document                                                                                                                              |
| status           | String       | Read Only          | The [status](#statuses) for the document                                                                                                                          |
| title            | String       | Required           | The document's title                                                                                                                                              |
| updated\_at      | Date Time    | Read Only          | Time stamp when the document was last updated                                                                                                                     |
| user             | ID           | Read Only          | The ID for the [user](#users) this document belongs to                                                                                                            |

[Expandable fields](#expandable-fields): user, organization, projects, sections, notes

### Uploading a Document

There are two supported ways to upload documents &mdash; directly uploading the
file to our storage servers or by providing a URL to a publicly available
PDF.  We currently only support PDF documents.

#### Direct File Upload Flow

1. `POST /api/documents/`

To initiate an upload, you will first create the document.  You may specify all
writable document fields (besides `file_url`).  The response will contain all
the fields for the document, with two being of note for this flow:
`presigned_url` and `id`.

2. `PUT <presigned_url>`

Next, you will `PUT` the binary data for the file to the given
`presigned_url`.  The presigned URL is valid for 5 minutes.  You may obtain a
new URL by issuing a `GET` request to `/api/documents/\<id\>/`

3. `POST /api/documents/<id>/process/`

Finally, you will begin processing of the document.  Note that this endpoint
accepts no additional parameters.

#### URL Upload Flow

1. `POST /api/documents/`

If you set `file_url` to a URL pointing to a publicly accessible PDF, our
servers will fetch the PDF and begin processing it automatically.

### Endpoints

* `GET /api/documents/` &mdash; List documents
* `POST /api/documents/` &mdash; Create document
* `PUT /api/documents/` &mdash; Bulk update documents
* `PATCH /api/documents/` &mdash; Bulk partial update documents
* `DELETE /api/documents/` &mdash; Bulk delete documents
    * Bulk delete will not allow you to indiscriminately delete all of your
      documents.  You must specify which document IDs you want to delete using
      the `id__in` filter.
* `POST /api/documents/process/` &mdash; Bulk process documents
    * This will allow you to process multiple documents with a single API call.
      It expects to receive a JSON object with a single property `ids`, which
      should be a list of IDs to re-process.
* `GET /api/documents/search/` &mdash; [Search](#search-help) documents
    * TODO: in depth search help
* `GET /api/documents/<id>/` &mdash; Get document
* `PUT /api/documents/<id>/` &mdash; Update document
* `PATCH /api/documents/<id>/` &mdash; Partial update document
* `DELETE /api/documents/<id>/` &mdash; Delete document
* `POST /api/documents/<id>/process/` &mdash; Process document
    * This will process a document.  It is used after uploading the file in the
      [direct file upload flow](#direct-file-upload-flow) or to reprocess a
      document, which you may want to do in the case of an error.  It does not
      accept any parameters.  Note that it is an error to try to process a
      document that is already processing.
* `DELETE /api/documents/<id>/process/` &mdash; Cancel processing document
    * This will cancel the processing of a document.  Note that it is an error
      to try to cancel the processing if the document is not processing.
* `GET /api/documents/<id>/search/` &mdash; [Search](#search-help) within a document

### Filters

* `ordering` &mdash; Sort the results &mdash; valid options include: `created_at`,
  `page_count`, `title`,  and `source`.  You may prefix any valid option with
  `-` to sort it in reverse order.
* `user` &mdash; Filter by the ID of the owner of the document.
* `organization` &mdash; Filter by the ID of the organization of the document.
* `project` &mdash; Filter by the ID of a project the document is in.
* `access` &mdash; Filter by the [access level](#access-levels).
* `status` &mdash; Filter by [status](#statuses).
* `created_at__lt`, `created_at__gt` &mdash; Filter by documents created
  either before or after a given date.  You may specify both to find documents
  created between two dates. This may be a date or date time, in the following
  formats: `YYYY-MM-DD` or `YYYY-MM-DD+HH:MM:SS`.
* `page_count`, `page_count__lt`, `page_count__gt` &mdash; Filter by documents
  with a specified number of pages, or more or less pages then a given amount.
* `id__in` &mdash; Filter by specific document IDs, passed in as comma
  separated values.

### Notes

Notes can be left on documents for yourself, or to be shared with other users.  They may contain HTML for formatting.

#### Fields

| Field        | Type      | Options            | Description                                                        |
| ---          | ---       | ---                | ---                                                                |
| ID           | Integer   | Read Only          | The ID for the note                                                |
| access       | String    | Default: `private` | The [access level](#access-levels) for the note                    |
| content      | String    | Not Required       | Content for the note, which may include HTML                       |
| created\_at  | Date Time | Read Only          | Time stamp when this note was created                               |
| edit\_access | Bool      | Read Only          | Does the current user have edit access to this note                |
| organization | Integer   | Read Only          | The ID for the [organization](#organizations) this note belongs to |
| page\_number | Integer   | Required           | The page of the document this note appears on                      |
| title        | String    | Required           | Title for the note                                                 |
| updated\_at  | Date Time | Read Only          | Time stamp when this note was last updated                          |
| user         | ID        | Read Only          | The ID for the [user](#users) this note belongs to                 |
| x1           | Float     | Not Required       | Left most coordinate of the note, as a percentage of page size     |
| x2           | Float     | Not Required       | Right most coordinate of the note, as a percentage of page size    |
| y1           | Float     | Not Required       | Top most coordinate of the note, as a percentage of page size      |
| y2           | Float     | Not Required       | Bottom most coordinate of the note, as a percentage of page size   |

[Expandable fields](#expandable-fields): user, organization

The coordinates must either all be present or absent &mdash; absent represents
a page level note which is displayed between pages.

#### Endpoints

* `GET /api/documents/<document_id>/notes/` - List notes
* `POST /api/documents/<document_id>/notes/` - Create note
* `GET /api/documents/<document_id>/notes/<id>/` - Get note
* `PUT /api/documents/<document_id>/notes/<id>/` - Update note
* `PATCH /api/documents/<document_id>/notes/<id>/` - Partial update note
* `DELETE /api/documents/<document_id>/notes/<id>/` - Delete note

### Sections

Sections can mark certain pages of your document &mdash; the viewer will show
an outline of the sections allowing for quick access to those pages.

#### Fields

| Field        | Type    | Options   | Description                                      |
| ---          | ---     | ---       | ---                                              |
| ID           | Integer | Read Only | The ID for the section                           |
| page\_number | Integer | Required  | The page of the document this section appears on |
| title        | String  | Required  | Title for the section                            |

#### Endpoints

* `GET /api/documents/<document_id>/sections/` - List sections
* `POST /api/documents/<document_id>/sections/` - Create section
* `GET /api/documents/<document_id>/sections/<id>/` - Get section
* `PUT /api/documents/<document_id>/sections/<id>/` - Update section
* `PATCH /api/documents/<document_id>/sections/<id>/` - Partial update section
* `DELETE /api/documents/<document_id>/sections/<id>/` - Delete section

### Errors

Sometimes errors happen &mdash; if you find one of your documents in an error
state, you may check the errors here to see a log of the latest, as well as
all previous errors.  If the message is cryptic, please contact us &mdash; we
are happy to help figure out what went wrong.

#### Fields

| Field       | Type      | Options   | Description                            |
| ---         | ---       | ---       | ---                                    |
| ID          | Integer   | Read Only | The ID for the error                   |
| created\_at | Date Time | Read Only | Time stamp when this error was created |
| message     | String    | Required  | The error message                      |

#### Endpoints

* `GET /api/documents/<document_id>/errors/` - List errors


### Data

Documents may contain user supplied metadata.  You may assign multiple values
to arbitrary keys.  This is represented as a JSON object, where each key has a
list of strings as a value.  The special key `_tag` is used by the front end to
represent tags.  These values are useful for searching and organizing documents.

#### Fields

| Field  | Type        | Options      | Description                      |
| ---    | ---         | ---          | ---                              |
| values | List:String | Required     | The values associated with a key |
| remove | List:String | Not Required | Values to be removed             |

`remove` is only used for `PATCH`ing.  `values` is not required when `PATCH`ing.

#### Endpoints

* `GET /api/documents/<document_id>/data/` - List values for all keys
    * The response for this is a JSON object with a property for each key,
      which will always be a list of strings, corresponding to the values
      associated with that key.  Example:
      ```
      {
        "_tag": ["important"],
        "location": ["boston", "new york"]
      }
      ```
* `GET /api/documents/<document_id>/data/<key>/` - Get values for the given key
    * The response for this is a JSON list of strings.  Example: `["one", "two"]`
* `PUT /api/documents/<document_id>/data/<key>/` - Set values for the given key
    * This will override all values currently under key
* `PATCH /api/documents/<document_id>/data/<key>/` - Add and/or remove values for the given key
* `DELETE /api/documents/<document_id>/data/<key>/` - Delete all values for a given key

### Redactions

Redactions allow you to obscure parts of the document which are confidential
before publishing them.  The pages which are redacted will be fully flattened
and reprocessed, so that the original content is not present in lower levels of
the image or as text data.  Redactions are not reversible, and may only be
created, not retrieved or edited.

#### Fields

| Field        | Type    | Options  | Description                                                           |
| ---          | ---     | ---      | ---                                                                   |
| page\_number | Integer | Required | The page of the document this redaction appears on                    |
| x1           | Float   | Required | Left most coordinate of the redaction, as a percentage of page size   |
| x2           | Float   | Required | Right most coordinate of the redaction, as a percentage of page size  |
| y1           | Float   | Required | Top most coordinate of the redaction, as a percentage of page size    |
| y2           | Float   | Required | Bottom most coordinate of the redaction, as a percentage of page size |

#### Endpoints

* `POST /api/documents/<document_id>/redactions/` - Create redaction

## Projects

Projects are collections of documents.  They can be used for organizing groups
of documents, or for collaborating with other users by sharing access to
private documents.

### Sharing Documents

Projects may be used for sharing documents.  When you add a collaborator to a
project, you may select one of three access levels:

* `view` - This gives the collaborator permission to view your documents that
  you have added to the project
* `edit` - This gives the collaborator permission to view or edit your
  documents you have added to the project
* `admin` - This gives the collaborator both view and edit permissions, as well
  as the ability to add their own documents and invite other collaborators to
  the project

Additionally, you may add public documents to a project, for organizational
purposes.  Obviously, no permissions are granted to your or your collaborators
when you add documents you do not own to your project &mdash; this is tracked
by the `edit_access` field on the [project membership](#project-documents).
When you add documents you or your organization do own, it will be added with
`edit_access` enabled by default.  You may override this using the API if you
would like to add your documents to a project, but not extend permissions to
any of your collaborators.  Also note that documents shared with you for
editing via another project may not be added to your own project with
`edit_access` enabled.  This means the original owner of a document may revoke
any access they have granted to others via projects at any time.

### Fields

| Field        | Type      | Options          | Description                                                |
| ---          | ---       | ---              | ---                                                        |
| ID           | Integer   | Read Only        | The ID for the project                                     |
| created\_at  | Date Time | Read Only        | Time stamp when this project was created                   |
| description  | String    | Not Required     | A brief description of the project                         |
| edit\_access | Bool      | Read Only        | Does the current user have edit access to this project     |
| private      | Bool      | Default: `false` | Private projects may only be viewed by their collaborators |
| slug         | String    | Read Only        | The slug is a URL safe version of the title                |
| title        | String    | Required         | Title for the project                                      |
| updated\_at  | Date Time | Read Only        | Time stamp when this project was last updated              |
| user         | ID        | Read Only        | The ID for the [user](#users) who created this project     |

### Endpoints

* `GET /api/projects/` - List projects
* `POST /api/projects/` - Create project
* `GET /api/projects/<id>/` - Get project
* `PUT /api/projects/<id>/` - Update project
* `PATCH /api/projects/<id>/` - Partial update project
* `DELETE /api/projects/<id>/` - Delete project

### Filters

* `user` &mdash; Filter by projects where this user is a collaborator
* `document` &mdash; Filter by projects which contain the given document
* `private` &mdash; Filter by private or public projects.  Specify either
  `true` or `false`.
* `slug` &mdash; Filter by projects with the given slug.
* `title` &mdash; Filter by projects with the given title.

### Project Documents

These endpoints allow you to browse, add and remove documents from a project

#### Fields

| Field        | Type    | Options                            | Description                                                                     |
| ---          | ---     | ---                                | ---                                                                             |
| document     | Integer | Required                           | The ID for the [document](#document) in the project                             |
| edit\_access | Bool    | Default: `true` if you have access | If collaborators of this project should be granted edit access to this document |

[Expandable fields](#expandable-fields): document

#### Endpoints

* `GET /api/projects/<project_id>/documents/` - List documents in the project
* `POST /api/projects/<project_id>/documents/` - Add a document to the project
* `PUT /api/projects/<project_id>/documents/` - Bulk update documents in the project
* `PATCH /api/projects/<project_id>/documents/` - Bulk partial update documents in the project
* `DELETE /api/projects/<project_id>/documents/` - Bulk remove documents from the project
    * You should specify which document IDs you want to delete using the
      `document_id__in` filter.  This endpoint *will* allow you to remove all
      documents in the project if you call it with no filter specified.
* `GET /api/projects/<project_id>/documents/<document_id>/` - Get a document in the project
* `PUT /api/projects/<project_id>/documents/<document_id>/` - Update document in the project
* `PATCH /api/projects/<project_id>/documents/<document_id>/` - Partial update document in the project
* `DELETE /api/projects/<project_id>/documents/<document_id>/` - Remove document from the project

#### Filters

* `document_id__in` &mdash; Filter by specific document IDs, passed in as comma
  separated values.

### Collaborators

Other users who you would like share this project with.  See [Sharing
Documents](#sharing-documents)

#### Fields

| Field  | Type    | Options         | Description                                                       |
| ---    | ---     | ---             | ---                                                               |
| access | String  | Default: `view` | The [access level](#sharing-documents) for this collaborator      |
| email  | Email   | Create Only     | Email address of user to add as a collaborator to this project    |
| user   | Integer | Read Only       | The ID for the [user](#user) who is collaborating on this project |

[Expandable fields](#expandable-fields): user

#### Endpoints

* `GET /api/projects/<project_id>/users/` - List collaborators on the project
* `POST /api/projects/<project_id>/users/` - Add a collaborator to the project
  &mdash; you must know the email address of a user with a DocumentCloud
  account in order to add them as a collaborator on your project
* `GET /api/projects/<project_id>/users/<user_id>/` - Get a collaborator in the project
* `PUT /api/projects/<project_id>/users/<user_id>/` - Update collaborator in the project
* `PATCH /api/projects/<project_id>/users/<user_id>/` - Partial update collaborator in the project
* `DELETE /api/projects/<project_id>/users/<user_id>/` - Remove collaborator from the project

## Organizations

Organizations represent a group of users.  They may share a paid plan and
resources with each other.  Organizations can be managed and edited from the
[MuckRock accounts site][3].  You may only view organizations through the
DocumentCloud API.

### Fields

| Field       | Type    | Options   | Description                                                                                             |
| ---         | ---     | ---       | ---                                                                                                     |
| ID          | Integer | Read Only | The ID for the organization                                                                             |
| avatar\_url | URL     | Read Only | A URL pointing to an avatar for the organization &mdash; normally a logo for the company                |
| individual  | Bool    | Read Only | Is this organization for the sole use of an individual                                                  |
| name        | String  | Read Only | The name of the organization                                                                            |
| slug        | String  | Read Only | The slug is a URL safe version of the name                                                              |
| uuid        | UUID    | Read Only | UUID which links this organization to the corresponding organization on the [MuckRock Accounts Site][3] |

### Endpoints

* `GET /api/organizations/` - List organizations
* `GET /api/organizations/<id>/` - Get an organization

## Users

Users can be managed and edited from the [MuckRock accounts site][3].  You may
view users and change your own [active organization](#active-organization) from
the DocumentCloud API.

### Fields

| Field         | Type         | Options   | Description                                                                             |
| ---           | ---          | ---       | ---                                                                                     |
| ID            | Integer      | Read Only | The ID for the user                                                                     |
| avatar\_url   | URL          | Read Only | A URL pointing to an avatar for the user                                                |
| name          | String       | Read Only | The user's full name                                                                    |
| organization  | Integer      | Required  | The user's [active organization](#active-organization)                                  |
| organizations | List:Integer | Read Only | A list of the IDs of the organizations this user belongs to                             |
| username      | String       | Read Only | The user's username                                                                     |
| uuid          | UUID         | Read Only | UUID which links this user to the corresponding user on the [MuckRock Accounts Site][3] |

[Expandable fields](#expandable-fields): organization

### Endpoints

* `GET /api/users/` - List users
* `GET /api/users/<id>/` - Get a user
* `PUT /api/users/<id>/` - Update a user
* `PATCH /api/users/<id>/` - Partial update a user

## oEmbed

[oEmbed][4]

TODO: explain how oEmbed works

### Fields

| Field     | Type    | Options  | Description                                 |
| ---       | ---     | ---      | ---                                         |
| url       | URL     | Required | The URL to get an embed code for            |
| maxwidth  | Integer |          | The maximum width of the embedded resource  |
| maxheight | Integer |          | The maximum height of the embedded resource |

### Endpoints

* `GET /api/oembed/` - Get an embed code for a given URL

## Appendix

### Access Levels

The access level allows you to control who has access to your document by
default.  You may also explicitly share a document with additional users by
collaborating with them on a [project](#projects).

* `public` &ndash; Anyone on the internet can search for and view the document
* `private` &ndash; Only people with explicit permission (via collaboration) have access
* `organization` &ndash; Only the people in your organization have access

For notes, the `organization` access level will extend access to all users with
edit access to the document &mdash; this includes [project](#projects)
collaborators.

### Statuses

The status informs you to the current status of your document.

* `success` &ndash; The document has been succesfully processed
* `readable` &ndash; The document is currently processing, but is readable during the operation
* `pending` &ndash; The document is processing and not currently readable
* `error` &ndash; There was an [error](#errors) during processing
* `nofile` &ndash; The document was created, but no file was uploaded yet

### Languages
<details>
<summary>Language choices</summary>

* ara &ndash; Arabic
* zho &ndash; Chinese (Simplified)
* tra &ndash; Chinese (Traditional)
* hrv &ndash; Croatian
* dan &ndash; Danish
* nld &ndash; Dutch
* eng &ndash; English
* fra &ndash; French
* deu &ndash; German
* heb &ndash; Hebrew
* hun &ndash; Hungarian
* ind &ndash; Indonesian
* ita &ndash; Italian
* jpn &ndash; Japanese
* kor &ndash; Korean
* nor &ndash; Norwegian
* por &ndash; Portuguese
* ron &ndash; Romanian
* rus &ndash; Russian
* spa &ndash; Spanish
* swe &ndash; Swedish
* ukr &ndash; Ukrainian

</details>

### Page Spec

The page spec is a compressed string that lists dimensions in pixels for every
page in a document. Refer to [ListCrunch][2] for the compression format. For
example, `612.0x792.0:0-447`

### Static Assets

The static assets for a document are loaded from different URLs depending on
its [access level](#access-levels).  Append the following to the `static_url`
returned to load the static asset:

| Asset      | Path                                                          | Description                                                     |
| ---        | ---                                                           | ---                                                             |
| Document   | documents/\<id\>/\<slug\>.pdf                                 | The original document                                           |
| Full Text  | documents/\<id\>/\<slug\>.txt                                 | The full text of the document, obtained from the PDF or via OCR |
| JSON Text  | documents/\<id\>/\<slug\>.txt.json                            | The text of the document, in a custom JSON format (see below)   |
| Page Text  | documents/\<id\>/pages/\<slug\>-p\<page number\>.txt          | The text for each page in the document                          |
| Page Image | documents/\<id\>/pages/\<slug\>-p\<page number\>-\<size\>.gif | An image of each page in the document, in various sizes         |

\<size\> may be one of `large`, `normal`, `small`, or `thumbnail`

#### TXT JSON Format

The TXT JSON file is a single file containing all of the text, but broken out
per page.  This is useful if you need the text per page for every page, as you
can download just a single file.  There is a top level object with an `updated`
key, which is a Unix time stamp of when the file was last updated.  There may
be an `is_import` key, which will be set to `true` if this document was
imported from legacy DocumentCloud.  The last key is `pages` which contains the
per page info.  It is a list of objects, one per page.  Each page object will
have a `page` key, which is a 0-indexed page number.  There is a `contents` key
which contains the text for the page.  There is an `ocr` key, which is the
version of OCR software used to obtain the text.  Finally there is an `updated`
key, which is a Unix time stamp of when this page was last updated.

### Expandable Fields

The API uses expandable fields in a few places, which are implemented by the
[Django REST - FlexFields][5] package.  It allows related fields, which would
normally be returned by ID, be expanded into the fully nested representation.
This allows you to save additional requests to the server when you need the
related information, but for the server to not need to serve this information
when it is not needed.

To expand one of the expandable fields, which are document in the fields
section for each resource, add the `expand` query parameter to your request:

`?expand=user`

To expand multiple fields, separate them with a comma:

`?expand=user,organization`

You may also expand nested fields if the expanded field has its own expandable
fields:

`?expand=user.organization`

To expand all fields:

`?expand=~all`


[1]: https://jwt.io/
[2]: https://pypi.org/project/listcrunch/
[3]: https://accounts.muckrock.com/
[4]: https://oembed.com
[5]: https://github.com/rsinger86/drf-flex-fields
