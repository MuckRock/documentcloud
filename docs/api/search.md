
# DocumentCloud Search

## Contents

* [Syntax](#syntax)
* [API](#api)

<!-- intra document search? -->

## Introduction

DocumentCloud's search is powered by [Solr][1], an open source search engine by the Apache Software Foundation.  Most of the search syntax is passed through directly to Solr &em; you can read [Solr's documentation][2] directly for information on how its syntax works.  This document will reiterate the parts of that syntax that are applicable to DocumentCloud, as well as parts of the search that are specific to DocumentCloud.

## Syntax

### Specifying Terms

You may specify either single words to search for, such as `document` or `report`, or a phrase of multiple words to be matched as a whole, by surrounding it in double quotes, such as `"the mueller report"`.

### Wildcard Searches

Terms can use `?` to match any single character.  For example `?oat` will match both goat and boat.  You may use `*` to match zero or more characters, so `J*` will match J, John, Jane or any other word beginning with a J.  You may use these in any position of a term - beggining, middle or end.

### Fuzzy Searches

By appending a `~` to a term you can perform a fuzzy search which will match close varients of the term based on edit distance.  [Edit distance][3] is the number of insertions, deletions, substitutions or transpositions needed to get from one word to another.  This can be useful for finding documents with misspelled words or with poor OCR.  By default `~` will allow an edit distance of 2, but you can specify an edit distance of 1 by using `~1`.  For example, `book~` will match book, books, and looks.

### Proximity Searches

Proimity searches allow you to search for multiple words within a certain distance of each other.  It is specified by using a `~` with a number after a phrase.  For example, `"mueller report"~10` will search for documents which contain the words mueller and report within 10 words of each other.

### Ranges

Range searches allow you to search for fields that fall within a certain range.  For example, `pages:[2 TO 20]` will search for all documents with 2 to 20 pages, inclusive.  You can use `{` and `}` for exclusive ranges, as well as mix and match them.  Although this is most useful on numeric and date [fields](#fields), it will also work on text fields: `[a TO c]` will match all text alphabetically between a and c.

You can also use `*` for either end of the range to make it open ended.  For example, `pages:[100 TO *]` will find all documents with at least 100 pages.

### Boosting

Boosting allows you to alter how the documents are scored.  You can make one of your search terms more important in terms of ranking.  Use the `^` operator with a number.  By default, terms have a boost of 1.  For example, `mueller^4 report` will search for documents containing mueller or report, but giving more weight to the term mueller.

### Fields

By default, text is searched through title and source boosted to 10, description boosted to 5, and text boosted to 1.  You can search any field specifically by using `field:term` syntax.  For example, to just search for documents with report in the title, you can use `title:report`.  The fielded search only affects a single term &em; so `title:mueller report` will search for mueller in the title, and report in the default fields.  You can use `title:"mueller report"` to search for the exact phrase "mueller report" in the title, or use [grouping](#grouping-terms), `title:(mueller report)` to search for mueller or report in the title.

### Boolean Operators

You can require or omit certain terms, or apply more complex boolean logic to queries.  You can require a term by prepending it with `+` and can omit a term by prepending it with `-`.  You can also omit a term by preceding it with `NOT`.  You can require multiple terms by combining them with `AND`, and require either (or both) terms by combining them with `OR`.  For example, `mueller AND report` requires both mueller and report be present.  `+mueller -report` would require mueller be present and require report to not be present.  By default, multiple terms are combined with `OR` &em; but see [filter fields](#filter-fields) for how they are handled specially.

### Grouping Terms

You can use parenthesis to group terms, allowing for complex queries, such as `(mueller OR watergate) AND report` to require either mueller or watergate, and report to appear.

### Specifying Dates and Times

Date times must be fully specified in the form `YYYY-MM-DDThh:mm:ssZ` where YYYY is the year, MM is the month, DD is the day, hh is the hour, mm is the minutes, and ss is the seconds.  T is the literal T character and Z is the literal Z character.  These are always expressed in UTC time.  You may optinally include fractional seconds.  (`YYYY-MM-DDThh:mm:ss.fZ`)
You may also use `NOW` to stand in for the current time.  This is most useful when combined with date time math, which allows you to add or subtract time in the following units:
`YEAR, MONTH, DAY, HOUR, MINUTE, SECOND, MILLISECOND`.  For example `NOW+1DAY` would be one day from now.  `NOW-2MONTHS` would be 2 months in the past.

You may also use `/` to round to the closest time unit.  For example, `NOW/HOUR` is the beginning of the current hour.  These can be combined: `NOW-1YEAR+2MONTHS/MONTH` would be the beginning of the month, 2 months past one year ago.  These are useful with ranged searches: `[NOW-1MONTH TO *]` would be all dates past one month ago.

### Sorting

You may sort using the syntax `sort:score`.  Possible sortings include:
* `score` (highest first)
* `created_at` (newest first)
* `page_count` (largest first)
* `title` (alphabetical)
* `source` (alphabetical)

These may be reversed by prepending a `-` (`sort:-page_count`).

### Autoescape Behavior
<!-- let user know it was triggered -->

### Filter Fields

#### How fields are combined (lack of boolean)

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
* text
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

[1]: https://lucene.apache.org/solr/
[2]: https://lucene.apache.org/solr/guide/6_6/the-standard-query-parser.html
[3]: https://en.wikipedia.org/wiki/Damerau%E2%80%93Levenshtein_distance
