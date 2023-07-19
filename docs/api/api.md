# The DocumentCloud API

All APIs besides the authentication endpoints are served from
<https://api.www.documentcloud.org/api>.

## Overview

The API end points are generally organized as `/api/<resource>/` representing
the entirety of the resource, and `/api/<resource>/<id>/` representing a single
resource identified by its ID. All REST actions are not available on every
endpoint, and some resources may have additional endpoints, but the following
are how HTTP verbs generally map to REST operations:

`/api/<resource>/`

| HTTP Verb | REST Operation        | Parameters                                                                   |
| --------- | --------------------- | ---------------------------------------------------------------------------- |
| GET       | List the resources    | May support parameters for filtering                                         |
| POST      | Create a new resource | Must supply all `required` fields, and may supply all non-`read only` fields |

`/api/<resource>/<id>/`

| HTTP Verb | REST Operation                | Parameters                                                                                                                                                                                                     |
| --------- | ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GET       | Display the resource          |                                                                                                                                                                                                                |
| PUT       | Update the resource           | Same as for creating - all required fields must be present. For updating resources `PATCH` is usually preferred, as it allows you to only update the fields needed. `PUT` support is included for completeness |
| PATCH     | Partially update the resource | Same as for creating, but all fields are optional                                                                                                                                                              |
| DELETE    | Destroy the resources         |                                                                                                                                                                                                                |

A select few of the resources support some bulk operations on the `/api/<resource>/` route:

| HTTP Verb | REST Operation      | Parameters                                                                                                                    |
| --------- | ------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| POST      | Bulk create         | A list of objects, where each object is what you would `POST` for a single object                                             |
| PUT       | Bulk update         | A list of objects, where each object is what you would `PUT` for a single object &mdash; except it must also include the ID   |
| PATCH     | Bulk partial update | A list of objects, where each object is what you would `PATCH` for a single object &mdash; except it must also include the ID |
| DELETE    | Bulk destroy        | Bulk destroys will have a filtering parameter, often required, to specify which resources to delete                           |

### Responses

Lists response will be of the form

```
{
    "next": <next url if applicable>,
    "previous": <previous url if applicable>,
    "results": <list of results>
}
```

with a 200 status code.  The document search route will also include a `count`
key, with a total count of all documents returned by the search.

Getting a single resource, creating and updating will return just the object.
Create uses a 201 status code and get and update will return 200.

Delete will have an empty response with a 204 status code.

Batch updates will contain a list of objects updated with a 200 status code.

Specifying invalid parameters will generally return a 400 error code with a
JSON object with a single `"error"` key, whose value will be an error message.
Specifying an ID that does not exist or that you do not have access to view
will return status 404. Trying to create or update a resource you do not have
permission to will return status 403.

### Pagination

All list views accept a `per_page` parameter, which specifies how many
resources to list per page. It is `25` by default and may be set up to `100`
for authenticated users. For anonymous users it is restricted to `25`. You
may register for a free account at <https://accounts.muckrock.com/> to use the
`100` limit. You may view subsequent pages by using the `next` URL.

#### Cursor Based Pagination

Page offset pagination does not scale well to a large number of pages.  For
improved performance, DocumentCloud uses a cursor based
pagination system.  Instead of a `page` parameter, there is a `cursor`
parameter, which accepts an opaque `cursor` which specifies the last value
seen.  To use this system, you must use the `next` and `previous` links as
returned by the API, as random access is not available.  This system also
restricts arbitrary ordering of the results, except for the document search
route, which will still allow re-ordering with cursor based pagination.

If the cursor based pagination breaks your workflow, you may continue to use
the old page-offset based pagination system for now.  In the future, this will
be disabled completely, and you will be forced to use the cursor based
pagination.  To use the page-offset based pagination, which also has a top
level `count` key with a total count of the objects returned for all list
queries, add a `version=1.0` query parameter to your API queries.  Be aware
that this will make your queries less performant, possibly to the point of them
being unusable.  This should only be used as a stop-gap solution while you
update your workflow to use the new cursor based pagination.  Please reach out
to [info@documentcloud.org](mailto:info@documentcloud.org) if you need
assistance moving to the new version.

### Sub Resources

Some resources also support sub resources, which is a resource that belongs to another. The general format is:

`/api/<resource>/<id>/<subresource>/`

or

`/api/<resource>/<id>/<subresource>/<subresource_id>/`

It generally works the same as a resource, except scoped to the parent resource.

TODO: Examples

### Filters

Filters on list views which have choices generally allow you to specify
multiple values, and will filter on all resources that match at least one
choices. To specify multiple parameters you may either supply a comma
separated list of IDs &mdash; `?parameter=1,2` &mdash; or by specify the
parameter multiple times &mdash; `?parameter=1&parameter=2`.

### Rate Limits

The DocumentCloud API is rate limited to 10 requests per second.  It also
allows bursts up to 20 requests.  This means if you exceed the the 10 request
per second limit, it will serve you up to 20 requests more quickly, while
keeping track of your average rate.  After the 20 requests are served,
additional requests will be rejected with an HTTP status of 503 until you again
fall under an average of 10 requests per second.  If you use the Python
DocumentCloud library, it will automatically throttle your requests to 10 per
second to avoid going over the rate limit.  If you are writing custom code,
please be mindful of the rate limits.

There is also a secondary limit of 500 requests per day for anonymous users.
If you exceed this limit, you will start receiving errors with an HTTP status
of 429.  In order to avoid this, please register for a free account at
<https://aacounts.muckrock.com/>.  Currently, there are no daily limits of
registered accounts, although this may change in the future.

## Authentication

Authentication happens at the MuckRock accounts server located at
<https://accounts.muckrock.com/>. The API provided there will supply you with
a [JWT][1] access token and refresh token in exchange for your username and
password. The access token should be placed in the `Authorization` header
preceded by `Bearer` - `{'Authorization': 'Bearer <access token>'}`. The
access token is valid for 5 minutes, after which you will receive a 403
forbidden error if you continue trying to use it. At this point you may use
the refresh token to obtain a new access token and refresh token. The refresh
token is valid for one day.

### POST /api/token/

| Param    | Type   | Description   |
| -------- | ------ | ------------- |
| username | String | Your username |
| password | String | Your password |

#### Response

    {'access': <access token>, 'refresh': <refresh token>}

### POST /api/refresh/

| Param   | Type   | Description   |
| ------- | ------ | ------------- |
| refresh | String | Refresh token |

#### Response

    {'access': <access token>, 'refresh': <refresh token>}

## Documents

The documents API allows you to upload, browse and edit documents. To add or
remove documents from a project, please see [project
documents](#project-documents).

### Fields

| Field                | Type         | Options            | Description                                                                                                                                                      |
| -------------------- | ------------ | ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ID                   | Integer      | Read Only          | The ID for the document                                                                                                                                          |
| access               | String       | Default: `private` | The [access level](#access-levels) for the document                                                                                                              |
| asset_url            | String       | Read Only          | The base URL to load this document's [static assets](#static-assets) from                                                                                        |
| canonical_url        | URL          | Read Only          | The canonical URL to view this document                                                                                                                          |
| created_at           | Date Time    | Read Only          | Time stamp when this document was created                                                                                                                        |
| data                 | JSON         | Not Required       | [Custom metadata](#data)                                                                                                                                         |
| description          | String       | Not Required       | A brief description of the document                                                                                                                              |
| edit_access          | Bool         | Read Only          | Does the current user have edit access to this document                                                                                                          |
| file_hash             | String       | Read Only          | A sha1 hash representation of the raw PDF data as a hexadecimal string.                                                                                       |
| file_url             | URL          | Create Only        | A URL to a publicly accessible document for the [URL Upload Flow](#url-upload-flow)                                                                              |
| force_ocr            | Bool         | Create Only        | Force OCR even if the PDF contains embedded text - only include if `file_url` is set, otherwise should set `force_ocr` on the call to the processing endpoint    |
| language             | String       | Default: `eng`     | The [language](#languages) the document is in                                                                                                                    |
| noindex              | Bool         | Not required       | Ask search engines and DocumentCloud search to not index this document                                                                                           |
| organization         | Integer      | Read Only          | The ID for the [organization](#organizations) this document belongs to                                                                                           |
| original_extension   | String       | Default: `pdf`     | The original file extension of the document you are seeking to upload. It must be a [supported file type](#supported-file-types)                                 |
| page_count           | Integer      | Read Only          | The number of pages in this document                                                                                                                             |
| page_spec            | Integer      | Read Only          | [The dimensions for all pages in the document](#page-spec)                                                                                                       |
| pages                | JSON         | Write Only         | Allows you to set page text via the API.  See [set page text](#set-page-text) for more information.                                                              |
| presigned_url        | URL          | Read Only          | The pre-signed URL to [directly](#direct-file-upload-flow) `PUT` the PDF file to                                                                                 |
| projects             | List:Integer | Create Only        | The IDs of the [projects](#projects) this document belongs to - this may be set on creation, but may not be updated. See [project documents](#project-documents) |
| publish_at           | Date Time    | Not Required       | A timestamp when to automatically make this document public                                                                                                      |
| published_url        | URL          | Not Required       | The URL where this document is embedded                                                                                                                          |
| related_article      | URL          | Not Required       | The URL for the article about this document                                                                                                                      |
| remaining            | JSON         | Read Only          | The number of pages left for text and image processing - only included if `remaining` is included as a `GET` parameter                                           |
| slug                 | String       | Read Only          | The slug is a URL safe version of the title                                                                                                                      |
| source               | String       | Not Required       | The source who produced the document                                                                                                                             |
| status               | String       | Read Only          | The [status](#statuses) for the document                                                                                                                         |
| title                | String       | Required           | The document's title                                                                                                                                             |
| updated_at           | Date Time    | Read Only          | Time stamp when the document was last updated                                                                                                                    |
| user                 | Integer      | Read Only          | The ID for the [user](#users) this document belongs to                                                                                                           |

[Expandable fields](#expandable-fields): user, organization, projects, sections, notes

### Uploading a Document

There are two supported ways to upload documents &mdash; directly uploading the
file to our storage servers or by providing a URL to a publicly available
PDF or other [supported file type](#supported-file-types). 
To upload another supported file type you will need to include the original_extension field documented above. 

#### Direct File Upload Flow

1. `POST /api/documents/` <br><br>
   To initiate an upload, you will first create the document. You may specify all
   writable document fields (besides `file_url`). The response will contain all
   the fields for the document, with two being of note for this flow:
   `presigned_url` and `id`. <br><br>
   If you would like to upload files in bulk, you may `POST` a list of JSON
   objects to `/api/documents/` instead of a single object. The response will
   contain a list of document objects.

2. `PUT <presigned_url>` <br><br>
   Next, you will `PUT` the binary data for the file to the given
   `presigned_url`. The presigned URL is valid for 5 minutes. You may obtain a
   new URL by issuing a `GET` request to `/api/documents/\<id\>/`. <br><br>
   If you are bulk uploading, you will still need to issue a single `PUT` to the
   corresponding `presigned_url` for each file.

3. `POST /api/documents/<id>/process/` <br><br>
   Finally, you will begin processing of the document. Note that this endpoint
   accepts only one optional parameter &mdash; `force_ocr` which, if set to true,
   will OCR the document even if it contains embedded text. <br><br>
   If you are uploading in bulk you can issue a single `POST` to
   `/api/document/process/` which will begin processing in bulk. You should pass
   a list of objects containing the document IDs of the documents you would like
   to being processing. You may optionally specify `force_ocr` for each document.

#### URL Upload Flow

1. `POST /api/documents/`

If you set `file_url` to a URL pointing to a publicly accessible PDF, our
servers will fetch the PDF and begin processing it automatically.

You may also send a list of document objects with `file_url` set to bulk upload
files using this flow.

### Endpoints

- `GET /api/documents/` &mdash; List documents
- `POST /api/documents/` &mdash; Create document
- `PUT /api/documents/` &mdash; Bulk update documents
- `PATCH /api/documents/` &mdash; Bulk partial update documents
- `DELETE /api/documents/` &mdash; Bulk delete documents
  - Bulk delete will not allow you to indiscriminately delete all of your
    documents. You must specify which document IDs you want to delete using
    the `id__in` filter.
- `POST /api/documents/process/` &mdash; Bulk process documents
  - This will allow you to process multiple documents with a single API call.
    Expect parameters: `[{"id": 1, "force_ocr": true}, {"id": 2}]`
    It expects a list of objects, where each object contains the ID of the
    document to process, and an optional boolean, `force_ocr`, which will OCR
    the document even if it contains embedded text if set to `true`
- `GET /api/documents/search/` &mdash; [Search][6] documents
- `GET /api/documents/<id>/` &mdash; Get document
- `PUT /api/documents/<id>/` &mdash; Update document
- `PATCH /api/documents/<id>/` &mdash; Partial update document
- `DELETE /api/documents/<id>/` &mdash; Delete document
- `POST /api/documents/<id>/process/` &mdash; Process document
  - This will process a document. It is used after uploading the file in the
    [direct file upload flow](#direct-file-upload-flow) or to reprocess a
    document, which you may want to do in the case of an error. It accepts
    one optional boolean parameter, `force_ocr`, which will OCR the document
    even if it contains embedded text if it is set to `true`. Note that it
    is an error to try to process a document that is already processing.
- `DELETE /api/documents/<id>/process/` &mdash; Cancel processing document
  - This will cancel the processing of a document. Note that it is an error
    to try to cancel the processing if the document is not processing.
- `GET /api/documents/<id>/search/` &mdash; [Search][6] within a document

### Filters

- `ordering` &mdash; Sort the results &mdash; valid options include: `created_at`,
  `page_count`, `title`, and `source`. You may prefix any valid option with
  `-` to sort it in reverse order.
- `user` &mdash; Filter by the ID of the owner of the document.
- `organization` &mdash; Filter by the ID of the organization of the document.
- `project` &mdash; Filter by the ID of a project the document is in.
- `access` &mdash; Filter by the [access level](#access-levels).
- `status` &mdash; Filter by [status](#statuses).
- `created_at__lt`, `created_at__gt` &mdash; Filter by documents created
  either before or after a given date. You may specify both to find documents
  created between two dates. This may be a date or date time, in the following
  formats: `YYYY-MM-DD` or `YYYY-MM-DD+HH:MM:SS`.
- `page_count`, `page_count__lt`, `page_count__gt` &mdash; Filter by documents
  with a specified number of pages, or more or less pages then a given amount.
- `id__in` &mdash; Filter by specific document IDs, passed in as comma
  separated values.

### Notes

Notes can be left on documents for yourself, or to be shared with other users. They may contain HTML for formatting.

#### Fields

| Field        | Type      | Options            | Description                                                        |
| ------------ | --------- | ------------------ | ------------------------------------------------------------------ |
| ID           | Integer   | Read Only          | The ID for the note                                                |
| access       | String    | Default: `private` | The [access level](#access-levels) for the note                    |
| content      | String    | Not Required       | Content for the note, which may include HTML                       |
| created_at   | Date Time | Read Only          | Time stamp when this note was created                              |
| edit_access  | Bool      | Read Only          | Does the current user have edit access to this note                |
| organization | Integer   | Read Only          | The ID for the [organization](#organizations) this note belongs to |
| page_number  | Integer   | Required           | The page of the document this note appears on                      |
| title        | String    | Required           | Title for the note                                                 |
| updated_at   | Date Time | Read Only          | Time stamp when this note was last updated                         |
| user         | ID        | Read Only          | The ID for the [user](#users) this note belongs to                 |
| x1           | Float     | Not Required       | Left most coordinate of the note, as a percentage of page size     |
| x2           | Float     | Not Required       | Right most coordinate of the note, as a percentage of page size    |
| y1           | Float     | Not Required       | Top most coordinate of the note, as a percentage of page size      |
| y2           | Float     | Not Required       | Bottom most coordinate of the note, as a percentage of page size   |

[Expandable fields](#expandable-fields): user, organization

The coordinates must either all be present or absent &mdash; absent represents
a page level note which is displayed between pages.

#### Endpoints

- `GET /api/documents/<document_id>/notes/` - List notes
- `POST /api/documents/<document_id>/notes/` - Create note
- `GET /api/documents/<document_id>/notes/<id>/` - Get note
- `PUT /api/documents/<document_id>/notes/<id>/` - Update note
- `PATCH /api/documents/<document_id>/notes/<id>/` - Partial update note
- `DELETE /api/documents/<document_id>/notes/<id>/` - Delete note

### Sections

Sections can mark certain pages of your document &mdash; the viewer will show
an outline of the sections allowing for quick access to those pages.

#### Fields

| Field       | Type    | Options   | Description                                      |
| ----------- | ------- | --------- | ------------------------------------------------ |
| ID          | Integer | Read Only | The ID for the section                           |
| page_number | Integer | Required  | The page of the document this section appears on |
| title       | String  | Required  | Title for the section                            |

#### Endpoints

- `GET /api/documents/<document_id>/sections/` - List sections
- `POST /api/documents/<document_id>/sections/` - Create section
- `GET /api/documents/<document_id>/sections/<id>/` - Get section
- `PUT /api/documents/<document_id>/sections/<id>/` - Update section
- `PATCH /api/documents/<document_id>/sections/<id>/` - Partial update section
- `DELETE /api/documents/<document_id>/sections/<id>/` - Delete section

### Errors

Sometimes errors happen &mdash; if you find one of your documents in an error
state, you may check the errors here to see a log of the latest, as well as
all previous errors. If the message is cryptic, please contact us &mdash; we
are happy to help figure out what went wrong.

#### Fields

| Field      | Type      | Options   | Description                            |
| ---------- | --------- | --------- | -------------------------------------- |
| ID         | Integer   | Read Only | The ID for the error                   |
| created_at | Date Time | Read Only | Time stamp when this error was created |
| message    | String    | Required  | The error message                      |

#### Endpoints

- `GET /api/documents/<document_id>/errors/` - List errors

### Data

Documents may contain user supplied metadata. You may assign multiple values
to arbitrary keys. This is represented as a JSON object, where each key has a
list of strings as a value. The special key `_tag` is used by the front end to
represent tags. These values are useful for searching and organizing documents.
You may directly set or update the data from the document endpoints, but these
additional endpoints are supplied to add or remove data on a per key basis.

#### Fields

| Field  | Type        | Options      | Description                      |
| ------ | ----------- | ------------ | -------------------------------- |
| values | List:String | Required     | The values associated with a key |
| remove | List:String | Not Required | Values to be removed             |

`remove` is only used for `PATCH`ing. `values` is not required when `PATCH`ing.

#### Endpoints

- `GET /api/documents/<document_id>/data/` - List values for all keys
  - The response for this is a JSON object with a property for each key,
    which will always be a list of strings, corresponding to the values
    associated with that key. Example:
    ```
    {
      "_tag": ["important"],
      "location": ["boston", "new york"]
    }
    ```
- `GET /api/documents/<document_id>/data/<key>/` - Get values for the given key
  - The response for this is a JSON list of strings. Example: `["one", "two"]`
- `PUT /api/documents/<document_id>/data/<key>/` - Set values for the given key
  - This will override all values currently under key
- `PATCH /api/documents/<document_id>/data/<key>/` - Add and/or remove values for the given key
- `DELETE /api/documents/<document_id>/data/<key>/` - Delete all values for a given key

### Redactions

Redactions allow you to obscure parts of the document which are confidential
before publishing them. The pages which are redacted will be fully flattened
and reprocessed, so that the original content is not present in lower levels of
the image or as text data. Redactions are not reversible, and may only be
created, not retrieved or edited.

#### Fields

| Field       | Type    | Options  | Description                                                           |
| ----------- | ------- | -------- | --------------------------------------------------------------------- |
| page_number | Integer | Required | The page of the document this redaction appears on                    |
| x1          | Float   | Required | Left most coordinate of the redaction, as a percentage of page size   |
| x2          | Float   | Required | Right most coordinate of the redaction, as a percentage of page size  |
| y1          | Float   | Required | Top most coordinate of the redaction, as a percentage of page size    |
| y2          | Float   | Required | Bottom most coordinate of the redaction, as a percentage of page size |

#### Endpoints

- `POST /api/documents/<document_id>/redactions/` - Create redaction

### Modifications

Modifications allow you to perform page modification operations on a document, including moving pages, rotating pages, copying pages, deleting pages, and inserting pages from other documents. Applying modifications effectively shuffles, removes, and copies pages, preserving and duplicating page information as needed (this includes page text and any annotations and sections attached to the page). No page text needs to be reprocessed or re-OCR'd. After successfully applying modifications, the document cannot be reverted.

#### Modification Specification

To support a flexible host of potential modifications, you must pass in the modifications as a JSON array that lists the operations to take place. The modification specification defines the pages that should compose the document post-modification and any operations such as rotation to apply to the pages. Each element of the modification array can have the following fields (instructive examples will be listed after the official specification):

| Field         | Description                                                                                                                                                                                                                                                                                                                                                                                           |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| page          | A comma-separated string of page ranges, which can include individual pages or hyphenated inclusive runs of pages. Page numbers are 0-based (the first page of the document is page `0`, and `0-9` refers to the first through the 10th page of the document). Valid examples of page ranges include `"7"`, `"0-499"`, `"0-5,8,11-13"`, and `0,0,0` (page numbers can be repeated to duplicate them). |
| id            | If unspecified, pull pages from the current document. Otherwise, pull pages from the document with the specified id.                                                                                                                                                                                                                                                                                  |
| modifications | An array of JSON objects defining modifications to take place. The only currently defined page modification operation is `rotate`, which rotates pages clockwise, counterclockwise, or halfway. Rotation is specified as `{"type": "rotate", "angle": <angle>}`, where `<angle>` is one of `cc`, `ccw`, or `hw` (corresponding to clockwise, counterclockwise, and halfway, respectively).            |

#### Example Specifications

The following examples assume you are modifying the Mueller Report, a 448-page document.

| Example                                                                                                                                                                                                                                                                                                                        | Description                                                                            |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------- |
| <pre>[{<br>&nbsp;&nbsp;"page": "0-447"<br>}]</pre>                                                                                                                                                                                                                                                                             | Leave the Mueller Report unchanged                                                     |
| <pre>[{<br>&nbsp;&nbsp;"page": "0-23,423-447"<br>}]</pre>                                                                                                                                                                                                                                                                      | Remove the middle 400 pages of the Mueller Report                                      |
| <pre>[{<br>&nbsp;&nbsp;"page": "0-23,423-447"<br>}]</pre>                                                                                                                                                                                                                                                                      | Duplicate the first 50 pages of the Mueller Report at the end of the document          |
| <pre>[{<br>&nbsp;&nbsp;"page": "0-447",<br>&nbsp;&nbsp;"modifications": [{<br>&nbsp;&nbsp;&nbsp;&nbsp;"type": "rotate",<br>&nbsp;&nbsp;&nbsp;&nbsp;"angle": "ccw"<br>&nbsp;&nbsp;}]<br>}]</pre>                                                                                                                                | Rotate all the pages of the Mueller Report counter-clockwise                           |
| <pre>[<br>&nbsp;&nbsp;{<br>&nbsp;&nbsp;&nbsp;&nbsp;"page": "0-49",<br>&nbsp;&nbsp;&nbsp;&nbsp;"modifications": [{<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"type": "rotate",<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"angle": "hw"<br>&nbsp;&nbsp;&nbsp;&nbsp;}]<br>&nbsp;&nbsp;},<br>&nbsp;&nbsp;{ "page": "50-447" }<br>]</pre> | Rotate just the first 50 pages of the Mueller Report 180 degrees                       |
| <pre>[<br>&nbsp;&nbsp;{ "page": "0-447" },<br>&nbsp;&nbsp;{<br>&nbsp;&nbsp;&nbsp;&nbsp;"page": "0-49",<br>&nbsp;&nbsp;&nbsp;&nbsp;"id": "2000000"<br>&nbsp;&nbsp;},<br>]</pre>                                                                                                                                                 | Import 50 pages of another document with id `2000000` at the end of the Mueller report |

#### Endpoints

- `POST /api/documents/<document_id>/modifications/` - Create modifications

### Entities

Entities can be extracted using Google Cloud's Natural Language API. Entity
extraction must be initalized manually per document and entities are read-only.

#### Fields

Top level fields

| Field      | Type   | Description                                                                        |
| ---------- | ------ | ---------------------------------------------------------------------------------- |
| entity     | Object | Object containing information about this particular entity                         |
| relevance  | Float  | An estimate as to how relevant this entity is to this document                     |
| occurences | List   | A list of occurence objects specifying where in the document this entity was found |

Fields for the entity object

| Field         | Type   | Description                                                    |
| ------------- | ------ | -------------------------------------------------------------- |
| name          | String | The name of the entity                                         |
| kind          | String | The [kind](#kind) of entity                                    |
| description   | String | A short description of the entity                              |
| mid           | String | The Knowledge Graph ID                                         |
| wikipedia_url | URL    | The Wikipedia URL for this entity                              |
| metadata      | Object | Additional metadata for the entity, based on its [kind](#kind) |

Fields for the occurence objects

| Field       | Type    | Description                                                                 |
| ----------- | ------- | --------------------------------------------------------------------------- |
| page        | Integer | The page of the document this occurs on                                     |
| offset      | Integer | The character offset into the document this occurs on                       |
| content     | String  | The content of this occurence (the occurence may not match the entity name) |
| page_offset | Integer | The character offset into the page this occurs on                           |
| kind        | String  | `proper` for proper nouns, `common` for common nouns or `unknown`           |

##### Kind

Entity kinds include

- `unknown`
- `person`
- `location`
- `organization`
- `event`
- `work_of_art`
- `consumer_good`
- `other`
- `phone_number` &mdash; metadata may include number, national_prefix, area_code and extension
- `address` &mdash; metadata may include street_number, locality, street_name, postal_code, country, broad_region, narrow_region, and sublocality
- `date` &mdash; metadata may include year, month and day
- `price` &mdash; metadata may include value and currency

#### Endpoints

- `GET /api/documents/<document_id>/entities/` - List entities for this document
- `POST /api/documents/<document_id>/entities/` - Begin extracting entities for this document (POST body is empty)
- `DELETE /api/documents/<document_id>/entities/` - Delete all entities for this document

#### Filters

- `kind` &mdash; Filter for entities with the given kind (may give multiple, comma seperated)
- `occurences` &mdash; Filter for entities with the given occurence kind (`proper` or `common`)
- `relevance__gt` &mdash; Filter for documents with the given relevance or higher
- `mid` &mdash; Boolean filter for entities which do or do not have a MID
- `wikipedia_url` &mdash; Boolean filter for entities which do or do not have a Wikipedia URL

## Projects

Projects are collections of documents. They can be used for organizing groups
of documents, or for collaborating with other users by sharing access to
private documents.

### Sharing Documents

Projects may be used for sharing documents. When you add a collaborator to a
project, you may select one of three access levels:

- `view` - This gives the collaborator permission to view your documents that
  you have added to the project
- `edit` - This gives the collaborator permission to view or edit your
  documents you have added to the project
- `admin` - This gives the collaborator both view and edit permissions, as well
  as the ability to add their own documents and invite other collaborators to
  the project

Additionally, you may add public documents to a project, for organizational
purposes. Obviously, no permissions are granted to your or your collaborators
when you add documents you do not own to your project &mdash; this is tracked
by the `edit_access` field on the [project membership](#project-documents).
When you add documents you or your organization do own, it will be added with
`edit_access` enabled by default. You may override this using the API if you
would like to add your documents to a project, but not extend permissions to
any of your collaborators. Also note that documents shared with you for
editing via another project may not be added to your own project with
`edit_access` enabled. This means the original owner of a document may revoke
any access they have granted to others via projects at any time.

### Fields

| Field             | Type      | Options          | Description                                                                       |
| ----------------- | --------- | ---------------- | --------------------------------------------------------------------------------- |
| ID                | Integer   | Read Only        | The ID for the project                                                            |
| created_at        | Date Time | Read Only        | Time stamp when this project was created                                          |
| description       | String    | Not Required     | A brief description of the project                                                |
| edit_access       | Bool      | Read Only        | Does the current user have edit access to this project                            |
| add_remove_access | Bool      | Read Only        | Does the current user have permission to add and remove documents to this project |
| private           | Bool      | Default: `false` | Private projects may only be viewed by their collaborators                        |
| slug              | String    | Read Only        | The slug is a URL safe version of the title                                       |
| title             | String    | Required         | Title for the project                                                             |
| updated_at        | Date Time | Read Only        | Time stamp when this project was last updated                                     |
| user              | ID        | Read Only        | The ID for the [user](#users) who created this project                            |

### Endpoints

- `GET /api/projects/` - List projects
- `POST /api/projects/` - Create project
- `GET /api/projects/<id>/` - Get project
- `PUT /api/projects/<id>/` - Update project
- `PATCH /api/projects/<id>/` - Partial update project
- `DELETE /api/projects/<id>/` - Delete project

### Filters

- `user` &mdash; Filter by projects where this user is a collaborator
- `document` &mdash; Filter by projects which contain the given document
- `private` &mdash; Filter by private or public projects. Specify either
  `true` or `false`.
- `slug` &mdash; Filter by projects with the given slug.
- `title` &mdash; Filter by projects with the given title.

### Project Documents

These endpoints allow you to browse, add and remove documents from a project

#### Fields

| Field       | Type    | Options                            | Description                                                                     |
| ----------- | ------- | ---------------------------------- | ------------------------------------------------------------------------------- |
| document    | Integer | Required                           | The ID for the [document](#document) in the project                             |
| edit_access | Bool    | Default: `true` if you have access | If collaborators of this project should be granted edit access to this document |

[Expandable fields](#expandable-fields): document

#### Endpoints

- `GET /api/projects/<project_id>/documents/` - List documents in the project
- `POST /api/projects/<project_id>/documents/` - Add a document to the project
- `PUT /api/projects/<project_id>/documents/` - Bulk update documents in the project
  - This will set the documents in the project to exactly match the list you
    pass in. This means any documents currently in the project not in the
    list will be removed, and any in the list not currently in the project
    will be added.
- `PATCH /api/projects/<project_id>/documents/` - Bulk partial update documents
  in the project
  - This endpoint will not create or delete any documents in the project. It
    will simply update the metadata for each document passed in. It expects
    every document in the list to already be included in the project.
- `DELETE /api/projects/<project_id>/documents/` - Bulk remove documents from
  the project
  - You should specify which document IDs you want to delete using the
    `document_id__in` filter. This endpoint _will_ allow you to remove all
    documents in the project if you call it with no filter specified.
- `GET /api/projects/<project_id>/documents/<document_id>/` - Get a document in the project
- `PUT /api/projects/<project_id>/documents/<document_id>/` - Update document in the project
- `PATCH /api/projects/<project_id>/documents/<document_id>/` - Partial update document in the project
- `DELETE /api/projects/<project_id>/documents/<document_id>/` - Remove document from the project

#### Filters

- `document_id__in` &mdash; Filter by specific document IDs, passed in as comma
  separated values.

### Collaborators

Other users who you would like share this project with. See [Sharing
Documents](#sharing-documents)

#### Fields

| Field  | Type    | Options         | Description                                                       |
| ------ | ------- | --------------- | ----------------------------------------------------------------- |
| access | String  | Default: `view` | The [access level](#sharing-documents) for this collaborator      |
| email  | Email   | Create Only     | Email address of user to add as a collaborator to this project    |
| user   | Integer | Read Only       | The ID for the [user](#user) who is collaborating on this project |

[Expandable fields](#expandable-fields): user

#### Endpoints

- `GET /api/projects/<project_id>/users/` - List collaborators on the project
- `POST /api/projects/<project_id>/users/` - Add a collaborator to the project
  &mdash; you must know the email address of a user with a DocumentCloud
  account in order to add them as a collaborator on your project
- `GET /api/projects/<project_id>/users/<user_id>/` - Get a collaborator in the project
- `PUT /api/projects/<project_id>/users/<user_id>/` - Update collaborator in the project
- `PATCH /api/projects/<project_id>/users/<user_id>/` - Partial update collaborator in the project
- `DELETE /api/projects/<project_id>/users/<user_id>/` - Remove collaborator from the project

## Organizations

Organizations represent a group of users. They may share a paid plan and
resources with each other. Organizations can be managed and edited from the
[MuckRock accounts site][3]. You may only view organizations through the
DocumentCloud API.

### Fields

| Field      | Type    | Options   | Description                                                                                             |
| ---------- | ------- | --------- | ------------------------------------------------------------------------------------------------------- |
| ID         | Integer | Read Only | The ID for the organization                                                                             |
| avatar_url | URL     | Read Only | A URL pointing to an avatar for the organization &mdash; normally a logo for the company                |
| individual | Bool    | Read Only | Is this organization for the sole use of an individual                                                  |
| name       | String  | Read Only | The name of the organization                                                                            |
| slug       | String  | Read Only | The slug is a URL safe version of the name                                                              |
| uuid       | UUID    | Read Only | UUID which links this organization to the corresponding organization on the [MuckRock Accounts Site][3] |

### Endpoints

- `GET /api/organizations/` - List organizations
- `GET /api/organizations/<id>/` - Get an organization

## Users

Users can be managed and edited from the [MuckRock accounts site][3]. You may
view users and change your own [active organization](#active-organization) from
the DocumentCloud API.

### Fields

| Field         | Type         | Options   | Description                                                                             |
| ------------- | ------------ | --------- | --------------------------------------------------------------------------------------- |
| ID            | Integer      | Read Only | The ID for the user                                                                     |
| avatar_url    | URL          | Read Only | A URL pointing to an avatar for the user                                                |
| name          | String       | Read Only | The user's full name                                                                    |
| organization  | Integer      | Required  | The user's [active organization](#active-organization)                                  |
| organizations | List:Integer | Read Only | A list of the IDs of the organizations this user belongs to                             |
| username      | String       | Read Only | The user's username                                                                     |
| uuid          | UUID         | Read Only | UUID which links this user to the corresponding user on the [MuckRock Accounts Site][3] |

[Expandable fields](#expandable-fields): organization

### Endpoints

- `GET /api/users/` - List users
- `GET /api/users/<id>/` - Get a user
- `PUT /api/users/<id>/` - Update a user
- `PATCH /api/users/<id>/` - Partial update a user

## Add-Ons

Add-Ons allow you to easily add custom features to DocumentCloud.  [Learn more
about Add-Ons][7].  Add-Ons are added by installing the [GitHub App][8] in the
repository you would like to use as an add-on.  The API allows you to view,
edit and run your add-ons.

### Fields

| Field         | Type         | Options          | Description                                                                         |
| ------------- | ------------ | ---------------- | ----------------------------------------------------------------------------------- |
| ID            | Integer      | Read Only        | The ID for the add-on                                                               |
| access        | String       | Read Only        | The [access level](#access-levels) for the add-on (will be settable in the future)  |
| active        | Bool         | Default: `false` | Whether this add-on is active for you                                               |
| created_at    | Date Time    | Read Only        | Time stamp when this add-on was created                                             |
| name          | String       | Read Only        | The name of the add-on (set in the configuration)                                   |
| organization  | Integer      | Not Required     | The ID for the [organization](#organizations) this add-on belongs to                |
| parameters    | JSON         | Read Only        | The contents of the config.yaml file from the repository, converted to JSON         |
| repository    | String       | Read Only        | The full name of the GitHub repository, including the account name                  |
| updated_at    | Date Time    | Read Only        | Time stamp when the add-on was last updated                                         |
| user          | Integer      | Read Only        | The ID for the [user](#users) this add-on belongs to                                |

Your active add-ons are showed to you in the web interface.

### Endpoints

- `GET /api/addons/` - List add-ons
- `GET /api/addons/<id>/` - Get an add-on
- `PUT /api/addons/<id>/` - Update an add-on
- `PATCH /api/addons/<id>/` - Partial update an add-on

### Filters

- `active` &mdash; Filter by only your active or inactive add-ons 
- `query` &mdash; Searches for add-ons which contain the query in their name or description

### Add-On Runs

Add-on runs represent an invocation of an add-on.  You create one to run the
add-on.  The add-on itself can then update the add-on run as a means of
supplying feedback to the caller.

#### Fields

| Field         | Type         | Options          | Description                                                                                                                                                                            |
| ------------- | ------------ | ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| UUID          | UUID         | Read Only        | The ID for the add-on run                                                                                                                                                              |
| addon         | Integer      | Required         | The ID of the add-on that is being ran                                                                                                                                                 |
| created_at    | Date Time    | Read Only        | Time stamp when this add-on was created                                                                                                                                                |
| dismissed     | Bool         | Default: `false` | Add-on runs are shown to the user until they are dismissed                                                                                                                             |
| file_name     | String       | Write Only       | The add-on must set this to the name of the file supplied to `presigned_url` after uploading the file to make it accessible to the user                                                |
| file_url      | URL          | Read Only        | The URL of a file uploaded via `presigned_url`                                                                                                                                         |
| message       | String       | Not Required     | Add-ons may set infromational messages to the user while running                                                                                                                       |
| parameters    | JSON         | Write Only       | The add-on specific data                                                                                                                                                               |
| presigned_url | URL          | Read Only        | Only included if you set the `upload_file` query parameter to the name of the file to upload.  This is a URL the add-on can directly `PUT` a file to in order to return it to the user |
| progress      | Integer      | Not Required     | Long running add-ons may set this as a percentage of their progress                                                                                                                    |
| status        | String       | Read Only        | The status of the run - `queued`, `in_progress`, `success`, or `failure`                                                                                                               |
| updated_at    | Date Time    | Read Only        | Time stamp when the add-on was last updated                                                                                                                                            |
| user          | Integer      | Read Only        | The ID for the [user](#users) who ran the add-on                                                                                                                                       |

#### Endpoints

- `POST /api/addon_runs/` - Create a new add-on run - this will start the run using GitHub actions
- `GET /api/addon_runs` - List add-on runs
- `GET /api/addon_runs<uuid>/` - Get an add-on run
- `PUT /api/addon_runs/<uuid>/` - Update an add-on run
- `PATCH /api/addon_runs/<uuid>/` - Partial update an add-on run

#### Filters

- `dismissed` &mdash; Filter by dismissed or not dismissed add-on runs


## oEmbed

Generate an embed code for a document using our [oEmbed][4] service.

### Fields

| Field     | Type    | Options  | Description                                       |
| --------- | ------- | -------- | ------------------------------------------------- |
| url       | URL     | Required | The URL for the document to get an embed code for |
| maxwidth  | Integer |          | The maximum width of the embedded resource        |
| maxheight | Integer |          | The maximum height of the embedded resource       |

### Endpoints

- `GET /api/oembed/` - Get an embed code for a given URL

## Appendix

### Access Levels

The access level allows you to control who has access to your document by
default. You may also explicitly share a document with additional users by
collaborating with them on a [project](#projects).

- `public` &ndash; Anyone on the internet can search for and view the document
- `private` &ndash; Only people with explicit permission (via collaboration) have access
- `organization` &ndash; Only the people in your organization have access

For notes, the `organization` access level will extend access to all users with
edit access to the document &mdash; this includes [project](#projects)
collaborators.

### Statuses

The status informs you to the current status of your document.

- `success` &ndash; The document has been succesfully processed
- `readable` &ndash; The document is currently processing, but is readable during the operation
- `pending` &ndash; The document is processing and not currently readable
- `error` &ndash; There was an [error](#errors) during processing
- `nofile` &ndash; The document was created, but no file was uploaded yet

### Supported File Types

| Format                                     | Extension                                       | Type                     | Notes                                                                       |
| ------------------------------------------ | ----------------------------------------------- | ------------------------ | --------------------------------------------------------------------------- |
| AbiWord                                    | ABW, ZABW                                       | Document                 |                                                                             |
| Adobe PageMaker                            | PMD, PM3, PM4, PM5, PM6, P65                    | Document, DTP            |                                                                             |
| AppleWorks word processing                 | CWK                                             | Document                 | Formerly called ClarisWorks                                                 |
| Adobe FreeHand                             | AGD, FHD                                        | Graphics / Vector        |                                                                             |
| Apple Keynote                              | KTH, KEY                                        | Presentation             |                                                                             |
| Apple Numbers                              | Numbers                                         | Spreadsheet              |                                                                             |
| Apple Pages                                | Pages                                           | Document                 |                                                                             |
| BMP file format                            | BMP                                             | Graphics / Raster        |                                                                             |
| Comma-separated values                     | CSV, TXT                                        | Text                     |                                                                             |
| CorelDRAW 6-X7                             | CDR, CMX                                        | Graphics / Vector        |                                                                             |
| Computer Graphics Metafile                 | CGM                                             | Graphics                 | Binary-encoded only; not those using clear-text or character-based encoding |
| Data Interchange Format                    | DIF                                             | Spreadsheet              |                                                                             |
| DBase, Clipper, VP-Info, FoxPro            | DBF                                             | Database                 |                                                                             |
| DocBook                                    | XML                                             | XML                      |                                                                             |
| Encapsulated PostScript                    | EPS                                             | Graphics                 |                                                                             |
| Enhanced Metafile                          | EMF                                             | Graphics / Vector / Text |                                                                             |
| FictionBook                                | FB2                                             | eBook                    |                                                                             |
| Gnumeric                                   | GNM, GNUMERIC                                   | Spreadsheet              |                                                                             |
| Graphics Interchange Format                | GIF                                             | Graphics / Raster        |                                                                             |
| Hangul WP 97                               | HWP                                             | Document                 | Newer "5.x" documents are not supported                                     |
| HPGL plotting file                         | PLT                                             | Graphics                 |                                                                             |
| HTML                                       | HTML, HTM                                       | Document, text           |                                                                             |
| Ichitaro 8/9/10/11                         | JTD, JTT                                        | Document                 |                                                                             |
| JPEG                                       | JPG, JPEG                                       | Graphics                 |                                                                             |
| Lotus 1-2-3                                | WK1, WKS, 123, wk3, wk4                         | Spreadsheet              |                                                                             |
| Macintosh Picture File                     | PCT                                             | Graphics                 |                                                                             |
| MathML                                     | MML                                             | Math                     |                                                                             |
| Microsoft Excel 2003 XML                   | XML                                             | Spreadsheet              |                                                                             |
| Microsoft Excel 4/5/95                     | XLS, XLW, XLT                                   | Spreadsheet              |                                                                             |
| Microsoft Excel 97–2003                    | XLS, XLW, XLT                                   | Spreadsheet              |                                                                             |
| Microsoft Excel 2007-2016                  | XLSX                                            | Spreadsheet              |                                                                             |
| Microsoft Office 2007-2016 Office Open XML | DOCX, XLSX, PPTX                                | Multiple formats         |                                                                             |
| Microsoft PowerPoint 97–2003               | PPT, PPS, POT                                   | Presentation             |                                                                             |
| Microsoft PowerPoint 2007-2016             | PPTX                                            | Presentation             |                                                                             |
| Microsoft Publisher                        | PUB                                             | Document, DTP            |                                                                             |
| Microsoft RTF                              | RTF                                             | Document                 |                                                                             |
| Microsoft Word 2003 XML (WordprocessingML) | XML                                             | Document                 |                                                                             |
| Microsoft Word                             | DOC, DOT, DOCX                                  | Document                 |                                                                             |
| Microsoft Works                            | WPS, WKS, WDB                                   | Multiple                 | Microsoft Works for Mac formats since 4.1                                   |
| Microsoft Write                            | WRI                                             | Document                 |                                                                             |
| Microsoft Visio                            | VSD                                             | Graphics / Vector        |                                                                             |
| Netpbm format                              | PGM, PBM, PPM                                   | Graphics / Raster        |                                                                             |
| OpenDocument                               | ODT, FODT, ODS, FODS, ODP, FODP, ODG, FODG, ODF | Multiple formats         |                                                                             |
| Open Office Base                           | ODB                                             | Database forms, data     |                                                                             |
| OpenOffice.org XML                         | SXW, STW, SXC, STC, SXI, STI, SXD, STD, SXM     | Multiple formats         |                                                                             |
| PCX                                        | PCX                                             | Graphics                 |                                                                             |
| Photo CD                                   | PCD                                             | Presentation             |                                                                             |
| PhotoShop                                  | PSD                                             | Graphics                 |                                                                             |
| Plain text                                 | TXT                                             | Text                     | Various encodings supported                                                 |
| Portable Document Format                   | PDF                                             | Document                 | Including hybrid PDF                                                        |

### Languages

- ara &ndash; Arabic
- zho &ndash; Chinese (Simplified)
- tra &ndash; Chinese (Traditional)
- hrv &ndash; Croatian
- dan &ndash; Danish
- nld &ndash; Dutch
- eng &ndash; English
- fra &ndash; French
- deu &ndash; German
- heb &ndash; Hebrew
- hun &ndash; Hungarian
- ind &ndash; Indonesian
- ita &ndash; Italian
- jpn &ndash; Japanese
- kor &ndash; Korean
- nor &ndash; Norwegian
- por &ndash; Portuguese
- ron &ndash; Romanian
- rus &ndash; Russian
- spa &ndash; Spanish
- swe &ndash; Swedish
- ukr &ndash; Ukrainian

### Page Spec

The page spec is a compressed string that lists dimensions in pixels for every
page in a document. Refer to [ListCrunch][2] for the compression format. For
example, `612.0x792.0:0-447`

### Static Assets

The static assets for a document are loaded from different URLs depending on
its [access level](#access-levels). Append the following to the `asset_url`
returned to load the static asset:

| Asset          | Path                                                           | Description                                                     |
| ----------     | -------------------------------------------------------------  | --------------------------------------------------------------- |
| Document       | documents/\<id\>/\<slug\>.pdf                                  | The original document                                           |
| Full Text      | documents/\<id\>/\<slug\>.txt                                  | The full text of the document, obtained from the PDF or via OCR |
| JSON Text      | documents/\<id\>/\<slug\>.txt.json                             | The text of the document, in a custom JSON format (see below)   |
| Page Text      | documents/\<id\>/pages/\<slug\>-p\<page number\>.txt           | The text for each page in the document                          |
| Page Positions | documents/\<id\>/pages/\<slug\>-p\<page number\>.position.json | The position of text on each page, in a custom JSON format      |
| Page Image     | documents/\<id\>/pages/\<slug\>-p\<page number\>-\<size\>.gif  | An image of each page in the document, in various sizes         |

\<size\> may be one of `large`, `normal`, `small`, or `thumbnail`

#### TXT JSON Format

The TXT JSON file is a single file containing all of the text, but broken out
per page. This is useful if you need the text per page for every page, as you
can download just a single file. There is a top level object with an `updated`
key, which is a Unix time stamp of when the file was last updated. There may
be an `is_import` key, which will be set to `true` if this document was
imported from legacy DocumentCloud. The last key is `pages` which contains the
per page info. It is a list of objects, one per page. Each page object will
have a `page` key, which is a 0-indexed page number. There is a `contents` key
which contains the text for the page. There is an `ocr` key, which is the
version of OCR software used to obtain the text. Finally there is an `updated`
key, which is a Unix time stamp of when this page was last updated.

#### Position JSON Format

The position JSON file constains position information for each word of text on
the page.  It is an optional file, which may be generated depending on the type
of OCR run on the document.  If it exists, it will be a JSON array, which
contains a JSON object for each word of text.  The object for each word will
have the following fields:

* `text` - The text for the current word
* `x1`, `x2`, `y1`, `y2` - The coordinates of the bounding box for this word on
  the page.  Each value will be between 0 and 1 and represents a percentage of
  the width or height of the page.


#### Set Page Text

The format to set the page text is similar to the text formats described above.
The `pages` field may be set to a JSON array of page objects, with the
following fields:

| Field                | Type                  | Options      | Description                                                                  |
| -------------------- | --------------------- | ------------ | ---------------------------------------------------------------------------- |
| page_number          | Integer               | Required     | The page number you would like to set the page text for, zero indexed        |
| text                 | String                | Required     | The updated text for the given page                                          |
| ocr                  | String                | Not Required | An optional identifier for the OCR engine used to generate this text         |
| positions            | Array of JSON Objects | Not Required | Optionally set the position of each word of text, see next table for details |

The `position` field in each `pages` object is a JSON array of position
objects, with the following fields:

| Field    | Type   | Options      | Description                                                      |
| -------- | ------ | ------------ | ---------------------------------------------------------------- |
| text     | String | Required     | A single word on the page                                        |
| x1       | Float  | Required     | Left most coordinate of the word, as a percentage of page size   |
| x2       | Float  | Required     | Right most coordinate of the word, as a percentage of page size  |
| y1       | Float  | Required     | Top most coordinate of the word, as a percentage of page size    |
| y2       | Float  | Required     | Bottom most coordinate of the word, as a percentage of page size |
| metadata | JSON   | Not Required | Any extra metadata that you would like to store with this word   |

Example JSON setting just the page text:

```
[
    {"page_number": 0, "text": "Page 1 text"},
    {"page_number": 1, "text": "Page 2 text"}
]
```

Example JSON setting the page text and word positions:

```
[
    {
        "page_number": 0,
        "text": "Page 1 text",
        "ocr": "my-ocr-engine",
        "positions": [
            {
                "text": "Page",
                "x1": 0.1,
                "x2": 0.2,
                "y1": 0.1,
                "y2": 0.2,
                "metadata": {"type": "word"}
            },
            {
                "text": "1",
                "x1": 0.3,
                "x2": 0.4,
                "y1": 0.1,
                "y2": 0.2,
                "metadata": {"type": "word"}
            },
            {
                "text": "text",
                "x1": 0.5,
                "x2": 0.6,
                "y1": 0.1,
                "y2": 0.2,
                "metadata": {"type": "word"}
            }
        ]
    }
]
```


### Expandable Fields

The API uses expandable fields in a few places, which are implemented by the
[Django REST - FlexFields][5] package. It allows related fields, which would
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
[6]: https://www.documentcloud.org/help/search/
[7]: https://www.documentcloud.org/help/add-ons/
[8]: https://github.com/apps/documentcloud-add-on
