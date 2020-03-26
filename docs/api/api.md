
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
    * [Static Assets](#statis-assets)

## Overview

Describe an overview of the API layout, things which are common across the whole API
IE PUT vs PATCH, format of response, etc

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

| Field            | Type         | Options            | Description                                                                                                            |
| ---              | ---          | ---                | ---                                                                                                                    |
| ID               | Integer      | Read Only          | The ID for the document                                                                                                |
| access           | String       | Default: `private` | The [access level](#access-levels) for the document                                                                    |
| asset\_url       | String       | Read Only          | The base URL to load this document's [static assets](#static-assets) from                                              |
| created\_at      | Date Time    | Read Only          | Timestamp when this document was created                                                                               |
| data             | JSON         | Read Only          | [Custom metadata](#data)                                                                                               |
| description      | String       | Not Required       | A brief description of the document                                                                                    |
| edit\_access     | Bool         | Read Only          | Does the current user have edit access to this document                                                                |
| file\_url        | URL          | Create Only        | A URL to a publicly accessible document for the [URL Upload Flow](#url-upload-flow)                                    |
| language         | String       | Default: `eng`     | The [language](#languages) the document is in                                                                          |
| organization     | Integer      | Read Only          | The ID for the [organization](#organizations) this document belongs to                                                 |
| page\_count      | Integer      | Read Only          | The number of pages in this document                                                                                   |
| page\_spec       | Integer      | Read Only          | [The dimensions for all pages in the document](#page-spec)                                                             |
| presigned\_url   | URL          | Read Only          | The pre-signed URL to [directly](#direct-file-upload-flow) `PUT` the PDF file to                                       |
| projects         | List:Integer | Read Only          | The IDs of the [projects](#projects) this document belongs to                                                          |
| related\_article | URL          | Not Required       | The URL for the article about this document                                                                            |
| remaining        | JSON         | Read Only          | The number of pages left for text and image processing - only included if `remaining` is included as a `GET` parameter |
| remote\_url      | URL          | Not Required       | The URL where this document is embedded                                                                                |
| slug             | String       | Read Only          | The slug is a URL safe version of the title                                                                            |
| source           | String       | Not Required       | The source who produced the document                                                                                   |
| status           | String       | Read Only          | The [status](#statuses) for the document                                                                               |
| title            | String       | Required           | The document's title                                                                                                   |
| updated\_at      | Date Time    | Read Only          | Timestamp when the document was last updated                                                                           |
| user             | ID           | Read Only          | The ID for the [user](#users) this document belongs to                                                                 |

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

Finally, you will begin procssing of the document.  Note that this endpoint
accepts no additional parameters.

#### URL Upload Flow

1. `POST /api/documents/`

If you set `file_url` to a URL pointing to a publicly accessible PDF, our
servers will fetch the PDF and begin processing it automatically.

### Endpoints

TODO: More details
TODO: Filter parameters
TODO: Bulk operations

* `GET /api/documents/` - List documents
* `POST /api/documents/` - Create document
* `PUT /api/documents/` - Bulk update documents
* `PATCH /api/documents/` - Bulk partial update documents
* `DELETE /api/documents/` - Bulk delete documents
* `POST /api/documents/process/` - Bulk process documents
* `GET /api/documents/search/` - [Search](#search-help) documents
* `GET /api/documents/<id>/` - Get document
* `PUT /api/documents/<id>/` - Update document
* `PATCH /api/documents/<id>/` - Partial update document
* `DELETE /api/documents/<id>/` - Delete document
* `POST /api/documents/<id>/process/` - Process document
* `DELETE /api/documents/<id>/process/` - Cancel processing document
* `GET /api/documents/<id>/search/` - Search within a document

### Notes

Notes can be left on documents for yourself, or to be shared with other users.  They may contain HTML for formatting.

#### Fields

| Field        | Type      | Options            | Description                                                        |
| ---          | ---       | ---                | ---                                                                |
| ID           | Integer   | Read Only          | The ID for the note                                                |
| access       | String    | Default: `private` | The [access level](#access-levels) for the note                    |
| content      | String    | Not Required       | Content for the note, which may include HTML                       |
| created\_at  | Date Time | Read Only          | Timestamp when this note was created                               |
| edit\_access | Bool      | Read Only          | Does the current user have edit access to this note                |
| organization | Integer   | Read Only          | The ID for the [organization](#organizations) this note belongs to |
| page\_number | Integer   | Required           | The page of the document this note appears on                      |
| title        | String    | Required           | Title for the note                                                 |
| updated\_at  | Date Time | Read Only          | Timestamp when this note was last updated                          |
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
* `GET /api/documents/<document_id>/notes/<id>` - Get note
* `PUT /api/documents/<document_id>/notes/<id>` - Update note
* `PATCH /api/documents/<document_id>/notes/<id>` - Partial update note
* `DELETE /api/documents/<document_id>/notes/<id>` - Delete note

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
* `GET /api/documents/<document_id>/sections/<id>` - Get section
* `PUT /api/documents/<document_id>/sections/<id>` - Update section
* `PATCH /api/documents/<document_id>/sections/<id>` - Partial update section
* `DELETE /api/documents/<document_id>/sections/<id>` - Delete section

### Errors

Sometimes errors happen &mdash; if you find one of your documents in an error
state, you may check the errors here to see a log of the latest, as well as
all previous errors.  If the message is cryptic, please contact us &mdash; we
are happy to help figure out what went wrong.

#### Fields

| Field       | Type      | Options   | Description                           |
| ---         | ---       | ---       | ---                                   |
| ID          | Integer   | Read Only | The ID for the error                  |
| created\_at | Date Time | Read Only | Timestamp when this error was created |
| message     | String    | Required  | The error message                     |

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
* `GET /api/documents/<document_id>/data/<key>` - Get values for the given key
* `PUT /api/documents/<document_id>/data/<key>` - Set values for the given key
* `PATCH /api/documents/<document_id>/data/<key>` - Add and/or remove values for the given key
* `DELETE /api/documents/<document_id>/data/<key>` - Delete all values for a given key

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

Projects are collections of documents.  They can be used for organizaing groups
of documents, or for collaborating with other users by sharing access to
private documents.

### Sharing Documents

TODO: Explanation of how access levels and sharing works

### Fields

| Field        | Type      | Options          | Description                                                |
| ---          | ---       | ---              | ---                                                        |
| ID           | Integer   | Read Only        | The ID for the project                                     |
| created\_at  | Date Time | Read Only        | Timestamp when this project was created                    |
| description  | String    | Not Required     | A brief description of the project                         |
| edit\_access | Bool      | Read Only        | Does the current user have edit access to this project     |
| private      | Bool      | Default: `false` | Private projects may only be viewed by their collaborators |
| slug         | String    | Read Only        | The slug is a URL safe version of the title                |
| title        | String    | Required         | Title for the project                                      |
| updated\_at  | Date Time | Read Only        | Timestamp when this project was last updated               |
| user         | ID        | Read Only        | The ID for the [user](#users) who created this project     |

### Endpoints

* `GET /api/projects/` - List projects
* `POST /api/projects/` - Create project
* `GET /api/projects/<id>/` - Get project
* `PUT /api/projects/<id>/` - Update project
* `PATCH /api/projects/<id>/` - Partial update project
* `DELETE /api/projects/<id>/` - Delete project

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
* `GET /api/projects/<project_id>/documents/<document_id>` - Get a document in the project
* `PUT /api/projects/<project_id>/documents/<document_id>` - Update document in the project
* `PATCH /api/projects/<project_id>/documents/<document_id>` - Partial update document in the project
* `DELETE /api/projects/<project_id>/documents/<document_id>` - Remove document from the project

### Collaborators

#### Fields

| Field  | Type    | Options         | Description                                                       |
| ---    | ---     | ---             | ---                                                               |
| access | String  | Default: `view` | The [access level](#project-access) for this collaborator         |
| email  | Email   | Create Only     | Email address of user to add as a collaborator to this project    |
| user   | Integer | Read Only       | The ID for the [user](#user) who is collaborating on this project |

[Expandable fields](#expandable-fields): user

#### Endpoints

* `GET /api/projects/<project_id>/users/` - List collaborators on the project
* `POST /api/projects/<project_id>/users/` - Add a collaborator to the project
* `GET /api/projects/<project_id>/users/<user_id>` - Get a collaborator in the project
* `PUT /api/projects/<project_id>/users/<user_id>` - Update collaborator in the project
* `PATCH /api/projects/<project_id>/users/<user_id>` - Partial update collaborator in the project
* `DELETE /api/projects/<project_id>/users/<user_id>` - Remove collaborator from the project

## Organizations

Organizations represent a group of users.  They may share a paid plan and
resources with each other.  Organizations can be managed and edited from the
[MuckRock accounts site][3].  You may only view organizations through the
DocumentCloud API.

### Fields

| Field       | Type    | Options   | Description                                                                                             |
| ---         | ---     | ---       | ---                                                                                                     |
| ID          | Integer | Read Only | The ID for the organization                                                                             |
| avatar\_url | URL     | Read Only | A URL poitning to an avatar for the organization &mdash; normally a logo for the company                |
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
| avatar\_url   | URL          | Read Only | A URL poitning to an avatar for the user                                                |
| name          | String       | Read Only | The user's full name                                                                    |
| organization  | Integer      | Required  | The user's [active organization](#active-organization)                                  |
| organizations | List:Integer | Read Only | A list of the IDs of the organizations this user belongs to                             |
| username      | String       | Read Only | The user's username                                                                     |
| uuid          | UUID         | Read Only | UUID which links this user to the corresponding user on the [MuckRock Accounts Site][3] |

### Endpoints

* `GET /api/users/` - List users
* `GET /api/users/<id>/` - Get a user
* `PUT /api/users/<id>/` - Update a user
* `PATCH /api/users/<id>/` - Partial update a user

## oEmbed

[oEmbed][4]

### Fields

| Field     | Type    | Options  | Description                                |
| ---       | ---     | ---      | ---                                        |
| url       | URL     | Required | The URL to get an embed code for           |
| maxwidth  | Integer |          | The maximum width of the embeded resource  |
| maxheight | Integer |          | The maximum height of the embeded resource |

### Endpoints

* `GET /api/iembed/` - Get an embed code for a given URL

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

| Asset      | Path                                                          |
| ---        | ---                                                           |
| Document   | documents/\<id\>/\<slug\>.pdf                                 |
| Full Text  | documents/\<id\>/\<slug\>.txt                                 |
| JSON Text  | documents/\<id\>/\<slug\>.txt.json (TODO: describe)           |
| Page Image | documents/\<id\>/pages/\<slug\>-p\<page number\>-\<size\>.gif |
| Page Text  | documents/\<id\>/pages/\<slug\>-p\<page number\>.txt          |

\<size\> may be one of `large`, `normal`, `small`, or `thumbnail`

[1]: https://jwt.io/
[2]: https://pypi.org/project/listcrunch/
[3]: https://accounts.muckrock.com/
[4]: https://oembed.com

