# DocumentCloud Search

## Contents

- [Syntax](#syntax)
- [API](#api)

## Introduction

DocumentCloud's search is powered by [Solr][1], an open source search engine by the Apache Software Foundation. Most of the search syntax is passed through directly to Solr — you can read [Solr's documentation][2] directly for information on how its syntax works. This document will reiterate the parts of that syntax that are applicable to DocumentCloud, as well as parts of the search that are specific to DocumentCloud.

## Syntax

### Specifying Terms

You may specify either single words to search for, such as `document` or `report`, or a phrase of multiple words to be matched as a whole, by surrounding it in double quotes, such as `"the mueller report"`.

### Wildcard Searches

Terms can use `?` to match any single character. For example `?oat` will match both goat and boat. You may use `*` to match zero or more characters, so `J*` will match J, John, Jane or any other word beginning with a J. You may use these in any position of a term — beginning, middle or end.

### Fuzzy Searches

By appending `~` to a term you can perform a fuzzy search which will match close variants of the term based on edit distance. [Edit distance][3] is the number of letter insertions, deletions, substitutions, or transpositions needed to get from one word to another. This can be useful for finding documents with misspelled words or with poor OCR. By default `~` will allow an edit distance of 2, but you can specify an edit distance of 1 by using `~1`. For example, `book~` will match book, books, and looks.

### Proximity Searches

Proximity searches allow you to search for multiple words within a certain distance of each other. It is specified by using a `~` with a number after a phrase. For example, `"mueller report"~10` will search for documents which contain the words mueller and report within 10 words of each other.

### Ranges

Range searches allow you to search for fields that fall within a certain range. For example, `pages:[2 TO 20]` will search for all documents with 2 to 20 pages, inclusive. You can use `{` and `}` for exclusive ranges, as well as mix and match them. Although this is most useful on numeric and date [fields](#fields), it will also work on text fields: `[a TO c]` will match all text alphabetically between a and c.

You can also use `*` for either end of the range to make it open ended. For example, `pages:[100 TO *]` will find all documents with at least 100 pages.

### Boosting

Boosting allows you to alter how the documents are scored. You can make one of your search terms more important in terms of ranking. Use the `^` operator with a number. By default, terms have a boost of 1. For example, `mueller^4 report` will search for documents containing mueller or report but give more weight to the term mueller.

### Fields

By default, text is searched through title and source boosted to 10, description boosted to 5, and text boosted to 1. You can search any field specifically by using `field:term` syntax. For example, to just search for documents with report in the title, you can use `title:report`. The fielded search only affects a single term — so `title:mueller report` will search for mueller in the title, and report in the default fields. You can use `title:"mueller report"` to search for the exact phrase "mueller report" in the title, or use [grouping](#grouping-terms), `title:(mueller report)` to search for mueller or report in the title.

### Boolean Operators

You can require or omit certain terms, or apply more complex boolean logic to queries. You can require a term by prepending it with `+` and can omit a term by prepending it with `-`. You can also omit a term by preceding it with `NOT`. You can require multiple terms by combining them with `AND`, and require either (or both) terms by combining them with `OR`. For example, `mueller AND report` requires both mueller and report be present. `+mueller -report` would require mueller be present and require report to not be present. By default, multiple terms are combined with `OR` — but see [filter fields](#filter-fields) for how they are handled specially. These boolean operators must be uppercase, or else they will be treated as search terms.

### Grouping Terms

You can use parentheses to group terms, allowing for complex queries, such as `(mueller OR watergate) AND report` to require either mueller or watergate, and report to appear.

### Specifying Dates and Times

Date times must be fully specified in the form `YYYY-MM-DDThh:mm:ssZ` where YYYY is the year, MM is the month, DD is the day, hh is the hour, mm is the minutes, and ss is the seconds. T is the literal T character and Z is the literal Z character. These are always expressed in UTC time. You may optionally include fractional seconds (`YYYY-MM-DDThh:mm:ss.fZ`).
You may also use `NOW` to stand in for the current time. This is most useful when combined with date time math, which allows you to add or subtract time in the following units:
`YEAR, MONTH, DAY, HOUR, MINUTE, SECOND, MILLISECOND`. For example `NOW+1DAY` would be one day from now. `NOW-2MONTHS` would be 2 months in the past.

You may also use `/` to round to the closest time unit. For example, `NOW/HOUR` is the beginning of the current hour. These can be combined: `NOW-1YEAR+2MONTHS/MONTH` would be the beginning of the month, 2 months past one year ago. These are useful with ranged searches: `[NOW-1MONTH TO *]` would be all dates past one month ago.

### Sorting

You may sort using the syntax `sort:<sort type>`. Possible sortings include:

- `score` (highest score first; default)
- `created_at` (newest first)
- `page_count` (largest first)
- `title` (alphabetical)
- `source` (alphabetical)

These may be reversed by prepending a `-` (`sort:-page_count`). You may use `order` as an alias to `sort`.

### Escaping Special Characters

Special characters may be escaped by preceding them with a `\` — for example, `\(1\+1\)` will search for a literal "(1+1)" in the text instead of using the characters’ special meanings. If your query contains a syntax error, the parser will automatically escape your query to make a best effort at returning relevant results. The [API response](#api) will contain a field `escaped` informing you if this auto-escape mechanism was triggered.

### Filter Fields

The following fields may be searched on, which will filter the resulting documents based on their properties. By default, all fields included in the query are treated as required (e.g. `user:1 report` will show only documents from user 1 scored by the text query “report”). If you include multiple of the same field, the query is equivalent to applying `OR` between each of the same field (e.g. `user:1 user:2 report` will show documents by user 1 or 2). If you include distinct fields, the query is equivalent to applying `AND` between each set of distinct fields (e.g. `user:1 user:2 tag:email` will find documents by user 1 or 2 and which are tagged as email). If you use any explicit boolean operators (`AND` or `OR`), that will take precedence (e.g. `(user:1 AND tag:email) OR (user:2 AND tag:contract)` would return documents by user 1 tagged as email as well as documents by user 2 tagged as contract. This allows you to make complex boolean queries using any available field.

Available fields:

- **user**
  - Specify using the user ID. Also accepts the slug preceding the ID for readability (e.g. `user:mitchell-kotler-1`). `account` is an alias for user.
- **organization**
  - Specify using the organization ID. Also accepts the slug preceding the ID for readability (e.g. `organization:muckrock-1`). `group` is an alias for organization.
- **access**
  - Specify the access level. Valid choices are `public`, `organization`, and `private`.
- **status**
  - Specify the status of the document. Valid choices are `success`, `readable`, `pending`, `error`, and `nofile`.
- **project**
  - Specify using the project ID. Also accepts the slug preceding the ID for readability (e.g. `project:panama-papers-1`). `projects` is an alias for project.
- **document**
  - Specify using the document ID. Also accepts the slug preceding the ID for readability (e.g. `document:mueller-report-1`). `id` is an alias for document.
- **language**
  - Specify the language the document is in. Valid choices include:
    - ara - Arabic
    - zho - Chinese (Simplified)
    - tra - Chinese (Traditional)
    - hrv - Croatian
    - dan - Danish
    - nld - Dutch
    - eng - English
    - fra - French
    - deu - German
    - heb - Hebrew
    - hun - Hungarian
    - ind - Indonesian
    - ita - Italian
    - jpn - Japanese
    - kor - Korean
    - nor - Norwegian
    - por - Portuguese
    - ron - Romanian
    - rus - Russian
    - spa - Spanish
    - swe - Swedish
    - ukr - Ukrainian
- **slug**
  - Specify the slug of the document.
- **created_at**
  - Specify the [date time](#specifying-dates-and-times) the document was created.
- **updated_at**
  - Specify the [date time](#specifying-dates-and-times) the document was last updated.
- **page_count**
  - Specify the number of pages the document has. `pages` is an alias for page_count.
- **data\_\***
  - Specify arbitrary key-value data pairs on the document (e.g. the search query `data_color: blue` returns documents with data `color`: `blue`).
- **tag**
  - This is an alias to `data__tag` which is used by the site as a simple tagging system.

### Text Fields

Text fields can be used to search for text in a particular field of the document. They are used to score the searches and are always treated as optional unless you use `+` or `AND` to require them.

- **title**
  - The title of the document.
- **source**
  - The source of the document.
- **description**
  - The description of the document.
- **text**
  - The full text of the document, as obtained by text embedded in the PDF or by OCR. `doctext` is an alias for text.
- **page_no\_\***
  - You may search the text on the given page of a document. To find all documents which contain the word report on page 2, you could use `page_no_2:report`.

## API

You may search via the API:

`GET /api/documents/search/`

You may pass the query as described above in the `q` parameter (e.g. `/api/documents/search/?q=some+text+user:1` to search for some text in documents by user 1). For all fielded searches, you may pass them in as standalone query parameters instead of in `q` if you prefer (e.g. `/api/documents/search/?q=some+text&user=1` is the same query as the previous example). You may also negate fields by preceding them with a `-` in this way (e.g. `/api/documents/search/?q=some+text&-user=1` to search for some text in documents not by user 1). You may specify the sort order using either `sort` or `order` as a parameter (e.g. `/api/documents/search/?q=some+text+order:title` and `/api/documents/search/?q=some+text&order=title` both search for some text in documents sorted by their title).

You can also specify `per_page`, `page`, and `expand` as you would for `/api/documents/`. `expand` may be `user` or `organization` (or both `user,organization`). The response will be in a JSON object like a list response:

```
{
    "count": <number of results on the current page>,
    "next": <next page url if applicable>,
    "previous": <previous page url if applicable>,
    "results": <list of results>,
    "escaped": <bool>
}
```

with the addition of the `escaped` property to specify if the query had a syntax error and needed to be autoescaped. Each document will also contain a `highlights` property, which will contain relevant snippets from the document containing the given search term.

```
{
    "count": 413,
    "next": "https://api.www.documentcloud.org/api/documents/search/?q=report&page=2",
    "previous": null,
    "results": [
        {
            "id": "20059100",
            "user": 100000,
            "organization": 10001,
            "access": "public",
            "status": "success",
            "title": "the-mueller-report",
            "slug": "the-mueller-report",
            "source": "gema_georgia_gov",
            "language": "eng",
            "created_at": "2020-04-05T13:36:08.507Z",
            "updated_at": "2020-04-24T18:47:52.985Z",
            "page_count": 448,
            "highlights": {
                "title": [
                    "the-mueller-<em>report</em>"
                ],
                "page_no_9": [
                    "-CrinP6te\nINTRODUCTION TO VOLUME T |\n\nThis <em>report</em> is submitted to the Attorey General pursuant to 28 C-F.R"
                ]
            },
            "data": {},
            "asset_url": "https://assets.documentcloud.org/"
        },
    ]
}
```

You may search within a document using the following endpoint:

`GET /api/documents/<doc_id>/search/`

This will return up to 25 highlights per page for your query. You may use the same search syntax as above, although most of the fielded queries will not be meaningful when searching within a single document.

Example response:

```
{
    "title": [
        "the-mueller-<em>report</em>"
    ],
    "page_no_9": [
        "-CrinP6te\nINTRODUCTION TO VOLUME T |\n\nThis <em>report</em> is submitted to the Attorey General pursuant to 28 C-F.R",
        " the Attorney\nGeneral a confidential <em>report</em> explaining the prosecution or declination decisions [the",
        " in detail in this <em>report</em>, the Special Counsel's investigation established that\nRussia interfered in"
    ],
    "page_no_10": [
        "\n‘overview of the two volumes of our <em>report</em>.\n\nThe <em>report</em> describes actions and events that the Special",
        ", the <em>report</em> points out\nthe absence of evidence or conflicts in the evidence about a particular fact or",
        " with\nconfidence, the <em>report</em> states that the investigation established that certain actions or events",
        "\n‘coordination in that sense when stating in the <em>report</em> thatthe investigation did not establish that the\n‘Trump",
        " Campaign coordinated with the Russian government in its election interference activities.\n\nThe <em>report</em> on"
    ]
}
```

[1]: https://lucene.apache.org/solr/
[2]: https://lucene.apache.org/solr/guide/6_6/the-standard-query-parser.html
[3]: https://en.wikipedia.org/wiki/Damerau%E2%80%93Levenshtein_distance
