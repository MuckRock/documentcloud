
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
* Auto escape (return field letting user know auto escape was triggered?)

## Fields

### Filter Fields

* user
* organization
* access
* status
* project
* document
* data\_\*
* language
* slug
* tag
* created\_at
* updated\_at
* page\_count

### Text Fields

* title
* source
* description
* doctext
* page\_no\_\*

## API

* q
* All fields
* sort / order
* per\_page
* page
* expand

`GET /api/documents/search/`

`GET /api/documents/<doc_id>/search/`
