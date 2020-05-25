
# DocumentCloud Search

## Contents

* [Syntax](#syntax)
* [API](#api)

<!-- intra document search? -->

## Syntax

* Field lookups
* Logic
* Sorting
* Wildcard
* Fuzzy
* Proximity
* Phrase
* Grouping
* Custom Weight
* Range Searches
* DateTime format

## Fields

### Filter Fields

### Text Fields

## API

* q
* All fields
* sort
* per\_page
* page
* expand

`GET /api/documents/search/`
| Param        | Type    | Description                                                                                            |
| ---          | ---     | ---                                                                                                    |
| q            | String  | Search query                                                                                           |
| user         | Integer | Filter by ID of the owner of the document                                                              |
| organization | Integer | Filter by ID of the organization of the document                                                       |
| access       | String  | Filter by the document's access: `public`, `private`, or `organization`                                |
| status       | String  | Filter by the document's status: `success`, `readable`, `pending`, `error`, `nofile`                   |
| project      | Integer | Filter by the ID of projects the document is a part of                                                 |
| document     | Integer | Filter by the ID of the document                                                                       |
| title        | String  | Text search on the title                                                                               |
| source       | String  | Text search on the source                                                                              |
| description  | String  | Text search on the description                                                                         |
| data\_\*     | String  | Search user specified metadata (`*`: has key, `!`: does not have key)                                  |
| order        | String  | How to sort the documents: `score`, `created_at`, `page_count`, `title`, `source`                      |
| per\_page    | Integer | How many documents to show per page of results                                                         |
| page         | Integer | Which page of results to return                                                                        |
| expand       | String  | Allows expanding of user and organization data (commas separated list of `user` and/or `organization`) |
