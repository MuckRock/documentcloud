# Fix problemmatic caching headers

Make the document retrieve endpoint emit cache headers that are aggressive
for old documents, safe for new edits, and honored consistently by both
Cloudflare and downstream clients.

## Scope

**This project is the API only** (plus the Cloudflare and S3 configuration
that sits in front of it). The frontend is a separate codebase, and
aligning it is a **separate project that follows this one** — stabilize the
API's caching behavior first, then make the frontend agree with it.

Practically, that means no step below blocks on a frontend change. The
frontend appears here only as observed behavior (it's a client of this API
and a useful check on what the edge actually does), never as a dependency.
Where the two currently disagree, the disagreement is recorded as input to
that later project rather than something to resolve now.

## Decisions settled 2026-07-30

1. **Purging is batched.** The `invalidate_cache` task takes a list of pks
   and chunks the payload, rather than one task per document.
2. **The zone is on Business, and `Cache-Tag` purge _is_ available**
   (corrected 2026-07-30). It was briefly assumed Enterprise-only and
   struck; in fact Cloudflare moved all purge methods to every plan on
   2025-04-01. Section (6) is reinstated as the recommended mechanism:
   Cloudflare purge is by `doc-{id}` tag, which reaches every `?expand=…`
   and per-`Origin` variant at once — the key spaces URL purge couldn't.
   This relaxes (4)'s "Only cache what we can purge" constraint; the one
   thing tags don't fix is the edge synthetic-`Last-Modified` in (3), which
   is a separate concern.
3. **(5) adds the API URL to the purge set** (via its `doc-{id}` tag) even
   though (4) hasn't shipped. URL purge is retained for CloudFront and the
   S3 asset, which aren't Cloudflare-tagged.
4. **The page-modification fix is folded into the (5) PR** rather than
   split out.
5. **`invalidate_cache()` always purges the frontend URLs**, dropping the
   `access == public` branch, rather than threading the pre-change access
   through. Purging a URL that was never cached is harmless, and it
   removes a state-dependent branch that was already wrong (5b).
6. **Slug changes are out of scope — there is no way to change a document
   slug.** Verified at every layer: the serializer marks it read-only
   (`serializers.py:219`, `:684`), `Document.save()` only assigns it when
   falsy (`document.py:279`), and Django admin lists it in
   `readonly_fields` (`admin.py:47-48`). The only other assignments are at
   creation (`serializers.py:484`) and one that copies the existing value
   unchanged (`serializers.py:768`). Defect (5c) is therefore unreachable
   and needs no code — but the constraint it describes is real, so **if a
   rename feature is ever added it must capture the old slug before saving
   and purge that URL too.**

## What's there today (live as of 2026-05-13)

```
GET /api/documents/5/        # last edited 2020-11-10
HTTP/2 200
cache-control: public, max-age=600, no-store
vary: Cookie, Accept, Origin, Accept-Language
last-modified: Wed, 13 May 2026 16:49:53 GMT    ← response time, not doc mtime
cf-cache-status: HIT
age: 11
```

A recent document (`/api/documents/1/`, edited 3 weeks ago) gets the
identical headers. No tiering by document age. The `no-store` directive
contradicts the `public, max-age=600` directive on the same header line;
Cloudflare is currently overriding it via a dashboard Cache Rule (hence
the `HIT`), but browsers and standards-compliant intermediaries will
follow `no-store` and skip the cache.

Conditional GET with `If-Modified-Since: Tue, 10 Nov 2020 16:23:31 GMT`
returns **200 not 304** — the API ignores `If-Modified-Since` today.

## Live re-verification 2026-07-30

Probe document (public, `status: success`, `revision_control: false`,
`updated_at: 2026-06-04T01:51:48.292830Z`):

- API (in scope) `https://api.www.documentcloud.org/api/documents/28191058/`
- frontend (reference only) `https://www.documentcloud.org/documents/28191058-just-do-it-computer-use-agents-exhibit-blind-goal-directedness/`

Re-run with a custom `User-Agent` so the traffic is identifiable in logs,
e.g. `curl -A "DocumentCloud-cache-audit/1.0 (+you@muckrock.com)"`.

Sections 1, 2 and 3 are confirmed **deployed and working in production**:

```
GET /api/documents/28191058/
HTTP/2 200
cache-control: public, max-age=600            ← no `no-store` (1)
vary: Accept, Origin, Accept-Language         ← no `Cookie` (2)
last-modified: Thu, 04 Jun 2026 01:51:48 GMT  ← real doc mtime, not response time (3)
cf-cache-status: MISS → HIT on repeat
```

Conditional GET is exact, including the microsecond-truncation boundary
that (3) called out — `updated_at` is `…01:51:48.292830Z` and:

| `If-Modified-Since`             | result |
| ------------------------------- | ------ |
| `Thu, 04 Jun 2026 01:51:48 GMT` | `304`  |
| `Thu, 04 Jun 2026 01:51:47 GMT` | `200`  |
| `Mon, 01 Jan 2035 00:00:00 GMT` | `304`  |
| `Tue, 10 Nov 2020 16:23:31 GMT` | `200`  |

`Last-Modified` per `expand` also behaves as (3) designed — each expanded
relation's own timestamp is folded in (`expand=organization` reported
`Thu, 30 Jul 2026 19:33:10`, i.e. hours old from Squarelet sync, vs the
document's own `Thu, 04 Jun`), and `~all` / nested expands correctly get
**no** `Last-Modified` from the origin.

Production `CACHE_CONTROL_MAX_AGE` is **600**, not the `base.py:583`
default of 300.

Three things this probe turned up are recorded in place below, all in
scope: the (3) fail-safe is overridden at the edge (see 3, "Edge defeats
the fail-safe"), `Vary: Origin` fragments the cache without bound (see the
risk bullet), and no S3 asset sends `Cache-Control` at all (see 7).

For the record, the frontend page returns `public, max-age=3600` with a
correct `last-modified` and a working `304`. That's 6× looser than the
API's 600 — noted as input to the follow-on frontend project, not
something this one resolves.

### 1. ✅ RESOLVED — Fix the contradictory `Cache-Control` (Cloudflare, not the app)

**Verified fixed 2026-07-20.** Re-curled `api.www.documentcloud.org/api/documents/28424240/`:
`cache-control: public, max-age=600` with no `no-store`, and a second
request now shows `cf-cache-status: HIT` / `age: 1` — Cloudflare is
actually caching the response. Whatever Cache Rule was appending
`no-store` has been corrected. `vary: Cookie` and the synthetic
`last-modified` (still pinned to response time, still no `304` on
`If-Modified-Since`) are unchanged — those are sections 2 and 3, not
this one.

**Ruled out:** `documentcloud/documents/views.py:116-117` and
`documentcloud/documents/decorators.py:28-43`.

Originally suspected a decorator collision — `conditional_cache_control(no_cache=True)`
on dispatch stacked with `anonymous_cache_control` on retrieve. Verified
against the running app this is not the cause: `conditional_cache_control`
only calls `patch_cache_control` `if "Cache-Control" not in response`
(decorators.py:19-20), so once `anonymous_cache_control` sets the header
on `retrieve`, the outer dispatch-level decorator is a no-op. Confirmed
live — curling `api.dev.documentcloud.org` (Django origin, no Cloudflare
in front, no `server: cloudflare`/`cf-ray`) returns a clean
`Cache-Control: public, max-age=300` with no `no-store` and no
`Last-Modified` at all. `documentcloud/documents/tests/test_views.py:332-362`
already asserts this clean behavior and passes. The outer decorator is
also _not_ redundant — it's what keeps every other `DocumentViewSet`
action (create, update, list, …) uncached; only `retrieve` overrides it.
(The comment saying so was dropped in `7465d223` "cleanup and simplify";
the two decorators are now bare at `views.py:116-117`.)

Checked nginx too (`config/nginx.conf.erb`) — it only does CORS,
rate-limiting, gzip, and real-IP mapping; no `add_header Cache-Control`,
`expires`, `proxy_hide_header`, or `proxy_ignore_headers`. It passes
Django's response headers through unchanged. Django's `MIDDLEWARE`
(`config/settings/base.py:166-181`) has no `ConditionalGetMiddleware`
either, and nothing else in the app sets `Last-Modified`.

Curling `api.www.documentcloud.org` (through Cloudflare, `cf-cache-status: MISS`
so this is close to origin's real response) reproduces the plan's original
trace exactly: `cache-control: public, max-age=600, no-store` plus a
synthetic `last-modified` pinned to the response timestamp (identical to
the `date` header) — neither of which the app or nginx produced in the
direct test above.

Action: this is a Cloudflare-side fix, not a code change. Audit the
Cloudflare Cache Rule / Transform Rule scoped to `documents/*` on the
production zone — it's appending `no-store` to the origin's
`Cache-Control` and injecting a fabricated `Last-Modified`. Reconcile
the rule so it stops contradicting the origin header instead of editing
`views.py`/`decorators.py`.

### 2. ✅ RESOLVED — Drop `Vary: Cookie` from anonymous responses

**Touch point:** `documentcloud/documents/decorators.py:28-43` (removed
`vary_on_cookie`), plus a new
`documentcloud/core/middleware.py:22-52::StripCookieVaryMiddleware`, wired into
`MIDDLEWARE` at `config/settings/base.py:169`, just before
`django.contrib.sessions.middleware.SessionMiddleware` (line 170).

Removing `vary_on_cookie` from the decorator alone did **not** work —
verified by debug-printing `request.session.accessed` inside the
decorator: it was already `True` before our view code ran at all.
Root cause: `DEFAULT_AUTHENTICATION_CLASSES` (`config/settings/base.py:420-424`)
lists `rest_framework.authentication.SessionAuthentication` first, and its
`authenticate()` does `getattr(request._request, 'user', None)`, which
forces Django's lazy `request.user` to resolve via `get_user(request)` →
`request.session[SESSION_KEY]`. Merely touching `request.session` sets
`.accessed = True`, and Django's own `SessionMiddleware.process_response`
unconditionally calls `patch_vary_headers(response, ("Cookie",))` whenever
that flag is set — for every request, anonymous or not, regardless of
anything in `decorators.py`. This happens in DRF's `perform_authentication()`
before the view method ever executes, so it can't be prevented from the
view/decorator layer.

Fix: since `SessionMiddleware`'s `Vary: Cookie` injection happens in the
response phase and can't be pre-empted, strip it back out afterward.
`StripCookieVaryMiddleware` runs after `SessionMiddleware` in the response
phase (by being listed before it in `MIDDLEWARE`) and removes `Cookie`
from `Vary` on any response explicitly marked `public` in `Cache-Control` —
scoped that way rather than site-wide so it only touches responses the app
already intended to be CDN-cacheable (currently just the anonymous branch
of `anonymous_cache_control`). The authenticated branch (`private, no-cache`)
is untouched and keeps `Vary: Cookie`, though it's moot for CDN purposes
since `private`/`no-cache` already prevents shared-cache storage.

Verified: `documentcloud/documents/tests/test_views.py::test_retrieve`
(no `Cookie` in `Vary` for anonymous) and `test_retrieve_auth` (`Cookie`
still in `Vary` for authenticated) both pass; full suite (621 tests)
passes.

### 3. ✅ RESOLVED — Send real `Last-Modified` and honor `If-Modified-Since` → 304

**Touch point:** `documentcloud/documents/views.py:650-720` (`retrieve` plus
`_retrieve_last_modified`), `views.py:136-138` (`CONDITIONAL_EXPANDS`),
`views.py:107-113` (`_max_updated_at`), and
`documentcloud/documents/models/document.py:115-117`.

Implemented via `get_conditional_response`, per the notes below — with one
extra fix found in testing: `If-Modified-Since` is truncated to whole
seconds when parsed off the wire, but `document.updated_at.timestamp()`
still carries microseconds, so the raw float was always greater than the
truncated header value and the endpoint never returned `304`. Fixed by
truncating with `int(instance.updated_at.timestamp())` before comparing
and before formatting the `Last-Modified` header. Verified via
`test_retrieve_last_modified`, `test_retrieve_not_modified`, and
`test_retrieve_modified_since_stale` — all pass.

`Document.updated_at = AutoLastModifiedField` is the right freshness
signal — confirmed not bumped on reads (no `hit_count` increment in the
view). DRF has no built-in `Last-Modified` mixin (checked — nothing in
the `rest_framework` package handles conditional requests); use Django's
own conditional-response machinery instead:

- `django.utils.cache.get_conditional_response(request, last_modified=document.updated_at.timestamp(), response=response)`
  called inside `retrieve()` does both jobs in one shot: it sets
  `Last-Modified` on `response` (instead of letting it default to
  response time), and it returns a `304 Not Modified` (no body) when
  `If-Modified-Since`/`If-None-Match` show nothing has changed —
  otherwise it returns `None` and `retrieve()` should return `response`
  as normal.
- Since `anonymous_cache_control` patches `Cache-Control` on whatever
  response `retrieve()` returns, a `304` still comes out with the
  correct cache headers — no extra wiring needed there.
- Considered `django.views.decorators.http.condition(last_modified_func=...)`
  instead, since `get_conditional_response` isn't itself a documented
  `django.utils.cache` API (checked against Django's official docs —
  only `patch_cache_control`, `get_max_age`, `patch_response_headers`,
  `add_never_cache_headers`, `patch_vary_headers`, `get_cache_key`,
  `learn_cache_key` are listed) whereas `condition()`/`last_modified()`
  are the documented public API for this exact feature. Decided against
  it: `last_modified_func` has no access to `self`, so it can't reuse
  `self.get_object()` — it'd need its own `Document.objects.filter(pk=...)`
  lookup, costing a second DB query on every non-304 request (one for the
  conditional check, one for serialization). Kept `get_conditional_response`
  — undocumented, but it's the literal internal engine `condition()` itself
  is built on, and it lets a single `self.get_object()` serve both the
  freshness check and the response body.

Multiplied across daily scraper crawls of static archive content this is
a large bandwidth win — and pairs naturally with `stale-while-revalidate`
in (4).

**Expand correctness fix:** `document.updated_at` is only a valid freshness
signal for the _bare_ document. The retrieve endpoint supports
`expand=user,organization,projects,sections,notes,revisions`, and none of
those relations bump `document.updated_at` when they change (checked:
`NoteViewSet.perform_update`, `SectionViewSet`, `Document.save()` — no
bridging signals). Project _membership_ changes are the exception: adding or
removing a document from a project explicitly does `updated_at=now()` on the
document (`projects/views.py`), so the `projects` expand is covered by
`document.updated_at` + `Project.updated_at`.

Two of the six relations exposed no modification timestamp at all, so they were
first given the standard `created_at`/`updated_at`
(`AutoCreatedField`/`AutoLastModifiedField`), migrations included, and exposed
in their serializers:

- **`Section`** — had neither (`documents/models/document.py`,
  `SectionSerializer`).
- **`Organization`** — had neither, only a Squarelet-sync `date_update`
  (`organizations/models.py`, `OrganizationSerializer`).
- **`User`** already inherits both from squarelet-auth's `SAUser`;
  **`Revision`** is append-only, so its `created_at` is the freshness signal.

With every top-level expandable relation now timestamped,
`_retrieve_last_modified` computes `Last-Modified` as the max of
`document.updated_at` and the timestamp of each _explicitly_ expanded relation.
It returns `None` — skip conditional handling, plain `200`, never a stale
`304` — for a nested (`notes.user`) or `~all` expansion (whose deep fields it
can't cheaply follow), or for any expand outside `CONDITIONAL_EXPANDS` (so a
future expandable relation fails safe until it's handled here;
`test_conditional_expands_cover_expandable_fields` pins the set to the
serializer's `expandable_fields`).

Efficiency: `sections`/`notes`/`projects` are already prefetched by
`get_queryset().preload()`/`get_object()`, so their max is read from the
prefetch cache (`_max_updated_at`) rather than issuing a redundant aggregate;
`revisions` aren't prefetched, so an indexed `MAX(created_at)` aggregate is
used, gated on `change_document` to match the serializer's edit-only exposure.

#### ⚠️ Edge defeats the fail-safe (found 2026-07-30, must fix before 4)

The `return None` fail-safe works at the origin but **is overridden by
Cloudflare in production.** When the origin omits `Last-Modified`,
something in the edge path injects one pinned to the response time, and
then answers conditional requests from its cached copy:

```
GET /api/documents/28191058/?expand=~all
last-modified: Thu, 30 Jul 2026 20:21:07 GMT   ← == `date`, i.e. synthetic
GET same URL, If-Modified-Since: Mon, 01 Jan 2035 00:00:00 GMT
HTTP/2 304                                      ← should be 200
```

Same for `notes.user` and `user.organization`. Isolated as follows:

- The synthetic header appears even on `cf-cache-status: MISS`, so it's
  injected in-path, not at cache-store time.
- With a fresh cache-buster query param (guaranteed no edge copy), a
  far-future `If-Modified-Since` returns **200** — so Django's fail-safe
  is correct, and the `304` is generated **by the edge from its own
  cached object**, using a timestamp that has nothing to do with content.

Impact today is bounded: the synthetic value is refreshed whenever the
edge object expires, so the staleness window is the 600s TTL — no worse
than ordinary TTL staleness. **Under (4) it stops being bounded.** A
`~all` response granted `s-maxage=2592000` would answer revalidation with
`304` for thirty days on content the app explicitly declined to make
conditional. The protection written in (3) would be a no-op in the one
environment that matters.

Options, cheapest first:

1. Have (4) treat `last_modified is None` as its own tier — short or no
   shared-cache TTL (`private`, or `s-maxage` in the tens of seconds).
   This keeps the fix in the app, where the test suite can pin it, and is
   the recommended route. Nested/`~all` requests are a small share of
   traffic, so little is lost.
2. Send a real `ETag` instead of nothing. A hash of the serialized body
   is valid for _any_ expand, nested included, and would remove the
   special case entirely — the origin then always has a validator, so
   there's nothing for the edge to synthesize. Costs serialization on
   every revalidation (no 304 short-circuit before `get_serializer`),
   which is exactly what `retrieve` currently avoids. Note the API sends
   **no `ETag` at all** today; only S3 assets do.
3. Strip the injected header with a Cloudflare Transform Rule. Fixes it
   for real clients but leaves nothing in the repo to prevent regression;
   worth doing _in addition to_ (1), not instead.

Covered by `test_retrieve_expand_notes_last_modified`,
`test_retrieve_expand_notes_not_modified`,
`test_retrieve_expand_sections_last_modified`,
`test_retrieve_expand_organization_last_modified`,
`test_retrieve_expand_nested_no_conditional`,
`test_retrieve_expand_all_no_conditional`, and
`test_conditional_expands_cover_expandable_fields`.

### 4. Age-based TTL tiers (the headline change)

**Touch point:** `documentcloud/documents/decorators.py:28-43`,
`config/settings/base.py:583` (`CACHE_CONTROL_MAX_AGE`, default 300).

Replace the constant `CACHE_CONTROL_MAX_AGE` with a tier function keyed
off `document.updated_at`:

| Age bucket      | `max-age` (browser) | `s-maxage` (CDN) | Extras                         |
| --------------- | ------------------- | ---------------- | ------------------------------ |
| Edited < 24h    | 60                  | 300              | —                              |
| Edited < 7d     | 300                 | 3600             | —                              |
| Edited < 90d    | 3600                | 86400            | `stale-while-revalidate=3600`  |
| Edited 90d – 5y | 86400               | 2592000          | `stale-while-revalidate=86400` |
| Edited > 5y     | 86400               | 31536000         | `stale-while-revalidate=86400` |

Implementation note: the decorator currently operates without view-level
data. The cleanest place to compute the tier is _inside_ the retrieve
view (where the `Document` instance is in hand), setting
`response["Cache-Control"]` directly after serialization — `retrieve`
already computes `int(instance.updated_at.timestamp())` for
`Last-Modified` (3), so the tier is a pure function of a value already in
hand. Note it must be set on the `304` branch too, not just the `200`.

Correction to the original note here: what keeps list/search uncached is
_not_ `anonymous_cache_control` (that decorator is what makes a response
publicly cacheable) — it's the dispatch-level
`conditional_cache_control(no_cache=True)` at `views.py:116`. Leave that
alone and it keeps covering every non-`retrieve` action for free. Two
further corrections:

- That decorator emits `no-cache`, not `no-store` (`patch_cache_control(no_cache=True)`).
  The `no-store` in the original trace came from Cloudflare, per (1).
- `NoteViewSet` (`views.py:1425-1427`) applies `anonymous_cache_control`
  to **both `retrieve` and `list`**, so `/api/documents/{id}/notes/` is
  already publicly cached at `CACHE_CONTROL_MAX_AGE` — with no
  `Last-Modified`, no conditional handling, and no invalidation path.
  Either bring it into the tiering/invalidation scheme or decide it stays
  flat; don't silently extend TTLs there. Note it will also be hit by the
  synthetic-`Last-Modified` problem in (3), for the same reason.

One further fact from the 2026-07-30 probe: **`s-maxage` is currently
unused anywhere.** The API sends only `max-age`, so Cloudflare's edge TTL
is derived from it. The tier table's browser/CDN split therefore
introduces `s-maxage` for the first time — confirm the zone's Cache Rule
doesn't have an explicit "Edge TTL" override that would ignore it (see the
risk bullet).

Ship the API tiers on their own; the frontend is out of scope here (see
Scope above). Note only that the two currently disagree — HTML
`max-age=3600` vs JSON `max-age=600` — so the follow-on project has a real
gap to close, not a rubber stamp.

#### Only cache what we can purge

Still the governing constraint — a long `s-maxage` is only safe on
something (5) can actually purge — but `Cache-Tag` on Business (6) changes
what "purgeable" covers, and that reshapes this section from the earlier
URL-purge-only revision.

With `Cache-Tag: doc-{id}` on the retrieve response, a single tag purge
clears the bare URL, **every `?expand=…` variant, and every per-`Origin`
variant at once** — so the two key spaces this section previously wrote off
as unpurgeable (unbounded expand strings, `Vary: Origin` fragmentation) are
now reachable. The tier table can therefore apply to expand variants too,
not just the bare canonical URL, without stranding uninvalidatable content.

That removes the _purge-reachability_ reason for forcing query-string
requests to a short flat TTL. **But one reason remains, and it's
independent:** the synthetic-`Last-Modified` edge problem in (3). Nested and
`~all` expansions send no origin `Last-Modified`, and the edge fabricates
one; a long `s-maxage` there means the edge answers revalidation with a
bogus `304` for the full TTL. So:

- **Bare URL and handled `expand` sets** (those in `CONDITIONAL_EXPANDS`,
  which carry a real `Last-Modified`): full tier table. Purgeable by
  `doc-{id}`, and no synthetic-validator problem.
- **`last_modified is None` requests** (nested like `notes.user`, or
  `~all`): short flat TTL regardless — not for purge reasons anymore, but
  because (3)'s fail-safe is defeated at the edge for exactly these. This
  is the option-1 fix from (3); a real `ETag` (option 2) would remove even
  this special case, since the origin would always carry a validator.

Net: `Cache-Tag` collapses the old two-problems-one-rule framing. The
purge-reachability problem is gone; the edge-validator problem is what's
left, and it's narrower (only `last_modified is None`, not every query
string).

✅ **Query strings are in the cache key** — verified 2026-07-30, so
per-variant caching works and there's no collision bug today.
`?expand=user` MISSed then HIT while the bare URL was already HIT, and the
bodies differ correctly (bare `user` is an `int`, expanded is an object).

✅ **`Vary` fragmentation no longer blocks (4).** The earlier open question
— whether purge-by-URL clears all `Vary` variants or just one — is moot for
the API URL under tag purge: `Cache-Tag` purge invalidates every variant of
a tagged response irrespective of `Vary`. Fixing `Vary: Origin` reverts to
a pure optimization (fewer redundant edge entries), not a prerequisite.

### 5. ✅ IMPLEMENTED — Extend the existing `invalidate_cache()` to plain edits

**Built on `400-invalidate-cache` (test-first).** What shipped, vs. the design
below:

- **Purge is now by `Cache-Tag` for the API** (6): `DocumentViewSet.retrieve`
  sets `Cache-Tag: doc-{id}` on both the `200` and `304` branches
  (`views.py`, via a new `Document.cache_tag` property). CloudFront and the S3
  asset still purge by URL/path.
- **`invalidate_cache_batch(documents)` is a module-level function** in
  `models/document.py` (not a method — keeps `Document` under pylint's
  public-method cap and pairs with the `_invalidate_cloudfront` /
  `_invalidate_cloudflare` helpers). It builds the CloudFront paths, Cloudflare
  file URLs, and `doc-{id}` tags for the whole batch. `files` and `tags` go in
  **separate** Cloudflare requests (the zone purge API is a `oneOf`), each
  chunked to `CLOUDFLARE_PURGE_LIMIT = 100` (Business cap).
- **The old single-document `Document.invalidate_cache()` method was removed** —
  it had no callers once the task moved to the batch path.
- **The task is variadic** (`invalidate_cache(*document_pks)`) so the input is
  always iterable: `.delay(pk)` for one, `.delay(*pks)` for a batch. It clears
  `cache_dirty` with a queryset `.update()` (see the `updated_at` fix below).
- **Call sites wired:** `perform_update` (via a new `_invalidate_edited_cache`
  helper that batches every non-processing-transition instance — covers plain
  edits _and_ `_update_access` public↔private flips), `Document.destroy()`, and
  a one-line `cache_dirty = True` in `ModificationViewSet.create` (page mods
  ride the existing processing-completion purge, like redaction).
- **Coverage:** `test_tasks.py` (variadic + `updated_at` not bumped),
  `test_models.py::TestDocumentCacheInvalidation` (tag/URL split, always-purge
  frontend, chunking, CloudFront, no-zone/empty no-ops), and `test_views.py`
  (`Cache-Tag` on 200/304, edit/access/bulk/destroy purge enqueue, page-mod
  flag). Full documents suite (442) green; pylint 10/10, no new disables.

The original design notes follow, unchanged.

**Touch point:** `documentcloud/documents/models/document.py:704-748`
(`Document.invalidate_cache`), `documentcloud/documents/tasks.py:414-420`
(the `invalidate_cache` Celery task), `documentcloud/documents/views.py:1165-1169`
(`_update_cache`, the only caller), `views.py:1714` (redaction), and
`document.py:284-292` (`Document.destroy`).

Good news: `invalidate_cache()` **already exists**, is already async (the
Celery task at `tasks.py:415`), and already purges both CloudFront and
Cloudflare. The work is wiring, not building.

**Correction to the original note:** it is not "called from two places."
There is exactly **one** purge call site, and it's indirect. The existing
mechanism is a deferred, flag-based one:

1. Something destructive sets `document.cache_dirty = True` — today only
   redaction (`views.py:1714`); the `cache_dirty` field is
   `document.py:183`. It isn't serializer-writable, so redaction is the
   sole entry point.
2. `_update_cache` (`views.py:1165-1169`) fires the purge only when
   `old_processing and not document.processing and document.cache_dirty` —
   i.e. on the update that transitions a document _out_ of processing.
3. The task purges, clears the flag, and saves (`tasks.py:415-420`).

Plain edits sidestep this entirely: a title/access PATCH never toggles
`processing`, so condition (2) is never satisfied and no purge ever
happens. Confirmed not called from:

- `perform_update` / PATCH (title, description, metadata, `data` field
  edits) — `views.py:1054-1114`.
- `_update_access` (`views.py:1116-1136`), the public → private flip that
  most needs immediate invalidation for privacy reasons.
- `Document.destroy()` (`document.py:284-292`) — soft-deletes, deletes
  files, removes from Solr, but never purges the CDN.
- Slug changes (which change the canonical URL).
- **Page modifications** (`DocumentModificationViewSet.create`,
  `views.py:1852-1879`) — not in the original list, but rotating,
  deleting, or reordering pages rewrites the PDF and every page image
  _at the same URLs_. Unlike redaction, it never sets `cache_dirty`, so
  even the existing processing-completion purge doesn't fire. This is a
  live bug today, independent of (4): the CDN keeps serving the
  pre-modification PDF for the full TTL.

Without this, the tier table in (4) is unsafe — an edit on a 5-year-old
doc would take up to a year to propagate.

The cheapest fix for page modifications specifically is one line —
`document.cache_dirty = True` next to the `status = Status.pending` at
`views.py:1870` — since it then rides the existing
processing-completion purge, exactly as redaction does.

#### Three defects in `invalidate_cache()` itself that block part 4

These aren't wiring; the method needs fixing before the new call sites
are worth adding.

**a. It never purges the API URL.** `public_urls` is built from
`CLOUDFLARE_HOSTS` × `get_absolute_url()` — i.e.
`https://www.documentcloud.org/documents/{pk}-{slug}/` and
`https://embed.documentcloud.org/…` (`production.py:76-79`) — plus the S3
asset URL. Nothing purges
`https://api.www.documentcloud.org/api/documents/{pk}/`, which is
precisely the response (4) is about to make cacheable for up to a year.
Part 5 has to add it, or part 4 ships with no way to invalidate the thing
it caches. **Decided: (5) adds it.**

The `?expand=…` variants are handled by `Cache-Tag`, not URL purge:
tagging the retrieve response `doc-{id}` (6) means one tag purge clears the
bare URL and every expand/`Origin` variant together, so the unbounded key
space never has to be enumerated. **Decided: (5) purges by tag as the
primary mechanism**, keeping URL purge for CloudFront and the S3 asset
(which aren't Cloudflare-tagged). See "Only cache what we can purge" in (4).

**b. Public → private purges the wrong set.** `invalidate_cache()`
branches on `if self.access == Access.public` (`document.py:731`) to
decide whether to include the frontend URLs. On a public → private flip,
`access` is _already_ private by the time any purge would run, so the
branch falls through to `public_urls = [asset_url]` and the cached public
copy of the page and API response is left in Cloudflare — the exact
failure the plan calls out as _the_ reason to ship this before (4).
**Decided: always purge the frontend URLs**, dropping the
`access == public` branch entirely. Purging a URL that was never cached is
harmless, and it removes a state-dependent branch that was already wrong.

**c. ~~Slug changes can't be purged after the fact.~~ Unreachable — no
slug mutation path exists.** Kept for the record because the underlying
constraint is real. Both `doc_path` (`document.py:300-302`) and
`get_absolute_url()` (`document.py:273-274`) derive from the _current_
slug, so a post-save purge could only ever clean the new URL and would
leave the stale one live. But nothing can change a slug: it's read-only in
the serializer (`serializers.py:219`, `:684`), `Document.save()` assigns
it only when falsy (`document.py:279`), and admin has it in
`readonly_fields` (`admin.py:47-48`). **No code needed now.** If a rename
feature is ever added, it must capture the old slug _before_ saving and
purge that URL too — the same way `perform_update` already snapshots
`old_accesses` / `old_processings` (`views.py:1078-1081`).

#### Design decision: batched (settled)

**Decided: batched.** `perform_update` handles **bulk** updates
(`views.py:1060-1073`), so per-document tasks would fan a 500-document
PATCH out into 500 purge calls. Batching is still the right shape, but
`Cache-Tag` (6) makes the arithmetic much friendlier:

- **Cloudflare purge is by tag** — one `doc-{id}` tag per document, and
  Business allows **100 operations per request** (bucket size 50, 10
  req/sec). So a 500-doc PATCH chunks into batches of 100 tags: 5 requests,
  not the ~70 that 3–4 URLs/doc against a 30-URL cap would have needed.
  This is the payoff from (6): one tag replaces the 3–4 URLs (× expand ×
  `Origin` variants) a document would otherwise contribute.
- **CloudFront and the S3 asset URL** still purge by path (they aren't
  Cloudflare-tagged), so the task collects those per batch as before.

Shape: teach the `invalidate_cache` task to accept a list of pks; build the
`doc-{id}` tag list for the Cloudflare tag purge and the CloudFront/S3 path
list, and chunk each to its cap. One task per request rather than per
document. That also fixes the task's current `document.save()` (see below),
since clearing `cache_dirty` for a batch wants a queryset `.update()`
anyway.

Access flips no longer need a separate immediate path — a batch enqueued
`on_commit` is already prompt, and the earlier argument for splitting them
out was really about (5b)'s inverted access check, which is now fixed
directly.

#### Also: the purge task bumps `updated_at`

`tasks.py:419-420` clears `cache_dirty` with a bare `document.save()`,
and `updated_at` is an `AutoLastModifiedField` — so **every cache
invalidation moves the document's modification time to now.** Harmless
today, but under (4) it silently demotes the document to the shortest TTL
tier and resets the `Last-Modified` from (3) even though nothing about
the document changed. Fix with `save(update_fields=["cache_dirty"])` or a
queryset `.update()` before shipping (4).

This is the single change that _unlocks_ the long TTLs in (4), and it
still makes sense as a standalone PR before everything else — but it is no
longer the "small" one the original plan assumed. Final scope: three new
call sites (`perform_update`, `_update_access`, `destroy`) plus the
page-modification one-liner, two fixes inside `invalidate_cache()` (a and
b — c is unreachable), switching the Cloudflare purge from URL-based to
`doc-{id}` tag-based (6) while keeping URL purge for CloudFront and the S3
asset, the batching path, and the `updated_at` fix. The page-modification
bullet and defects (a) and (b) are worth fixing regardless of whether (4)
ever ships. Emitting the `Cache-Tag` header itself lands with (4)/(6);
(5)'s purge-by-tag assumes it's present, so if (5) ships first it should
add the header in the retrieve view at the same time.

#### Follow-ups deferred out of the (5) implementation

Surfaced by the post-implementation cleanup pass; both are real but
deliberately out of scope for this branch, so they're recorded here rather
than bolted on:

- **Two staleness conventions.** Plain edits now purge directly (batched via
  `_invalidate_edited_cache`), while redaction and page modifications set
  `cache_dirty` and drain on processing-completion (`_update_cache`), and
  `destroy()` enqueues from the model. The split is intentional and sound —
  a naive `post_save`/signal unification would be _worse_, since it can't
  batch a bulk edit into one purge and can't see the
  `old_processing → done` transition, both of which the view layer
  legitimately has. The remaining smell is purely that "this document is
  stale" is expressed in two conventions. Deeper direction if it ever earns
  the churn: make `cache_dirty` the single source of truth — set it wherever
  staleness is introduced (plain edits included) and drain dirty docs with
  one batched on-commit mechanism, collapsing `_update_cache` +
  `_invalidate_edited_cache` into one.
- **`Cache-Tag` is document-only.** `DocumentViewSet.retrieve` emits
  `doc-{id}` and (5) purges it, but `NoteViewSet` is also publicly cached
  (see the note in (4)) and is neither tagged nor purged when a note is
  edited — a real latent gap, not just missing polish. Deeper direction: a
  small `CacheTaggedMixin` with a `get_cache_tag(obj)` hook that stamps
  `response["Cache-Tag"]` in `finalize_response`, so both the 200/304
  branches and other cacheable viewsets (notes) adopt tagging uniformly;
  pair it with a note-edit purge path. Tracks alongside the `NoteViewSet`
  decision already flagged in (4).

#### Rate limiting under burst load

Cloudflare's purge API is rate-limited **per account** (shared across every
zone on the plan). On Business: **10 requests/second**, a burst bucket of
**50**, and **100 operations per request** (source: the availability table in
(6)). DocumentCloud regularly sees bursts of edits from users running bulk-edit
scripts, so this is a live concern, not theoretical.

What the (5) implementation already does about it:

- **Minimizes request volume.** A bulk PATCH is one `invalidate_cache` task
  that chunks to ≤100 tags/URLs per request, so a 500-doc bulk edit is ~5 file
  - ~5 tag requests — inside the 50-token burst bucket.
- **Absorbs 429s.** A `429` is a non-`ok` response, so it's logged (at
  `warning`, since it's expected/transient — real failures stay at `error`)
  and raised as `HTTPError`; the task's `autoretry_for=(RequestException,)` +
  `retry_backoff=30` retries it. Purging is idempotent and `cache_dirty` is
  only cleared on success, so nothing is lost.
- **Avoids a retry stampede.** Celery's `retry_backoff` defaults to
  `retry_jitter=True`, so a batch of simultaneously-throttled tasks retries at
  randomized delays rather than re-bursting in lockstep.

What it does **not** do: proactively pace to stay under the limit. A script
firing thousands of _individual_ PATCHes still queues thousands of tasks that
the default `celery` worker (concurrency 8) drains as fast as it can, so the
account limit is hit and worked around reactively (429 → retry) rather than
avoided. Correct, but noisy and slower to converge.

Escalation path if the 429 warnings become frequent in production
(preferred → lighter):

1. **Dedicated low-concurrency queue.** Route `invalidate_cache` to its own
   queue (the codebase already does this for `solr_*` via
   `CELERY_TASK_ROUTES`, consumed by the `solr_worker` dyno) and give it a
   worker with low concurrency. This bounds the global request rate at the
   source, drains FIFO, and needs no guesswork — but it is a **deploy step**
   (a new or repurposed worker dyno consuming the queue). Do not route to a
   queue with no consumer, or purges silently never run.
2. **Task `rate_limit`.** A one-line `@shared_task(rate_limit="…")` is
   tempting but is enforced **per worker instance**, not globally, so with
   multiple worker dynos it can't actually cap the account-wide rate; it only
   dampens per-worker bursts. Weaker than (1), and it can delay
   privacy-critical `public → private` purges behind a backlog of routine
   ones — so prefer (1).

### 6. Add `Cache-Tag` headers — AVAILABLE on Business (was thought Enterprise-only)

**Corrected 2026-07-30.** An earlier revision struck this as
Enterprise-only. That was stale: as of
[2025-04-01](https://developers.cloudflare.com/changelog/post/2025-04-01-purge-for-all/)
Cloudflare moved **all** purge methods — Purge by Tag included, and setting
`Cache-Tag` on origin responses — to **all plans**. Confirmed against the
current docs; the zone is on Business, which supports it. This flips
`Cache-Tag` from "off the table" back to the recommended purge mechanism,
and it is no longer "optional polish" — it's what makes the long TTLs in
(4) safe for anything with a query string.

**Business-plan purge limits** (per account, shared across same-plan zones;
[source](https://developers.cloudflare.com/cache/how-to/purge-cache/#availability-and-limits)):

|                            | Business    |
| -------------------------- | ----------- |
| Requests                   | 10 / second |
| Bucket size                | 50          |
| Max operations per request | 100         |

**Tag rules** (all plans): printable ASCII only (`0x21`–`0x7E`, no spaces /
Unicode / control chars), ≤1024 chars per tag, ≤1000 tags per response,
case-insensitive matching, invalid tags silently dropped at store time.

**Plan:** set `Cache-Tag: doc-{id}` on the retrieve response wherever (4)
sets `Cache-Control` (and on `NoteViewSet`, tagged `doc-{document_id}` so a
document purge clears its notes too). Then (5) purges by tag instead of by
URL: one `doc-{id}` purge invalidates the bare URL, **every `?expand=…`
variant, and every per-`Origin` variant at once** — precisely the key
spaces URL purge can't enumerate. Optionally add `project-{n}` / `org-{n}`
tags later for bulk project/org invalidation, but `doc-{id}` alone unblocks
(4) and (5).

Why this matters beyond convenience: it dissolves the central design
constraint this plan had been building around. See the rewritten "Only
cache what we can purge" in (4) and defect (5a).

One nuance it does **not** solve: the synthetic-`Last-Modified` edge
problem in (3) is about the _origin omitting a validator_, not about
purge reachability. `Cache-Tag` makes nested/`~all` responses purgeable but
does nothing about the edge fabricating a `Last-Modified` for them — that
still needs the (3) fix (short TTL for the `last_modified is None` case, a
real `ETag`, or a Transform Rule). Keep the two concerns separate.

### 7. Long-TTL on S3 assets

**Touch point:** the S3 bucket policy / object metadata for
`s3.documentcloud.org`, or a Cloudflare Transform Rule at the edge for
that hostname.

Public PDFs and page images are content-addressed (URLs are
deterministic by document id, and PDFs are also content-hashed via the
frontend's `?t={updated_at_ms}` cache-buster — see frontend
recommendations). They never change after processing. Set
`Cache-Control: public, max-age=31536000, immutable` on the S3 objects
(or add it via Transform Rule), and browsers + CDN can hold them
indefinitely. This change has no risk because the URL changes if the
underlying document is re-processed.

**Confirmed undone, 2026-07-30.** No S3 asset sends `Cache-Control` or
`Expires` at all — verified on all three asset types for the probe
document:

| asset                          | size    | `Cache-Control` | `ETag` | `Last-Modified` | `cf-cache-status` |
| ------------------------------ | ------- | --------------- | ------ | --------------- | ----------------- |
| `…/{slug}.pdf`                 | 8.67 MB | _absent_        | yes    | yes             | MISS → cached     |
| `…/pages/{slug}-p1-normal.gif` | 184 KB  | _absent_        | yes    | yes             | MISS → HIT        |
| `…/pages/{slug}-p1.txt`        | —       | _absent_        | yes    | yes             | MISS              |

With no `Cache-Control`, Cloudflare falls back to its default TTL for the
file extension and **browsers fall back to heuristic freshness**
(conventionally ~10% of `now - Last-Modified`), so they revalidate far
more often than these never-changing objects warrant. The assets do carry
`ETag` + `Last-Modified`, so revalidation is at least cheap — but at
8.67 MB for one PDF this is almost certainly the largest single bandwidth
item in the whole plan, well above the JSON savings from (3). It's a
config change with no code dependency and the biggest byte win, which is
why it moved up the PR sequence.

**The `?t={updated_at_ms}` cache-buster is not ours to rely on.** The
original note here justified `immutable` by pointing at that query param —
but it's generated by the frontend, a separate codebase outside this
project's scope, and it only protects clients that route through the
frontend's link. The underlying S3 key is `documents/{id}/{slug}.pdf`,
stable across re-processing, and the page-image keys carry no cache-buster
at all. So the safety argument has to stand on the S3 side alone:
`immutable` + `max-age=31536000` on a mutable key is only safe if every
rewrite of that key is paired with a purge — which is exactly the path in
(5). Page modifications rewrite these exact keys in place — see the
page-modification bullet in (5).

And a purge alone doesn't rescue it: **Cloudflare purge clears the edge,
not browsers.** A client that already holds
`max-age=31536000, immutable` will not revalidate for a year no matter
what's purged, so a redaction or page modification would leave that client
on the old PDF indefinitely — a privacy problem in the redaction case, not
just a staleness one. Two ways out, pick before shipping:

- **Version the key** (content hash or `updated_at` in the S3 path, not a
  query param) so a rewrite produces a genuinely new URL. Then `immutable`
  is honest. Costs a change to `common/path.py` and a migration of
  existing objects.
- **Split the directives** — long `s-maxage` (edge, purgeable by (5)) with
  a modest `max-age` and no `immutable` (browsers revalidate cheaply
  against the existing `ETag`). Captures most of the bandwidth win, keeps
  correctness, and needs no key changes. Recommended unless the assets get
  versioned keys.

### 8. Don't cache list / search endpoints

Today's behavior on `/api/documents/?…` and the search endpoint is
correct — query space is too large to cache whole-response usefully.
Leave as-is. Per-row caching at the search-engine layer is a separate
concern (see `solr-elasticsearch-migration/` for prior research).

Two accuracy notes: the app emits `no-cache` here, not `no-store` (from
`conditional_cache_control(no_cache=True)` at `views.py:116`); and this
does **not** hold for all list endpoints — `NoteViewSet.list` is
explicitly public-cached, see the note in (4).

## Recommended PR sequence (backend-only)

Numbers in parentheses refer to the sections above.

1. ✅ **Drop `no-store` (1) + drop `Vary: Cookie` for anonymous (2).**
   Shipped. The `no-store` half turned out to be a Cloudflare rule, not a
   code change; the `Vary` half needed `StripCookieVaryMiddleware`.
2. ✅ **Real `Last-Modified` + 304 on `If-Modified-Since` (3).** Shipped,
   including the expand-aware `_retrieve_last_modified` and the
   `Section`/`Organization` timestamp migrations it required.
3. ✅ **Extend `invalidate_cache()` to `perform_update`, `_update_access`,
   deletion, page modifications (5).** Implemented on branch
   `400-invalidate-cache`; must ship _before_ (4). Ended up larger than the
   original scope: two live defects in `invalidate_cache()` (missing API URL,
   inverted access check) fixed alongside the new call sites, the purge
   switched to `doc-{id}` `Cache-Tag` for the API, the task made variadic +
   batched, and the `updated_at`-bump-on-purge bug fixed. The third defect
   (slug change) was ruled unreachable — no slug mutation path exists. Also
   emits the `Cache-Tag` header (part of 6), since (5) shipped first.
4. **S3 `Cache-Control: immutable` (7).** Moved up from 5th: the
   2026-07-30 probe found the assets send no `Cache-Control` at all, and
   at 8.67 MB for a single PDF this is the biggest byte win in the plan.
   Config-only, no code dependency, independent of everything above.
5. **Age-based TTL tiers (4)** in the retrieve view. Ships on its own —
   no frontend coordination required (see Scope). After (3) so it's safe.
   Also needs: `Cache-Tag: doc-{id}` on the response (6), the tiering rule
   from "Only cache what we can purge" (full table for the bare URL and
   handled expands, short flat TTL for the `last_modified is None` case on
   edge-validator grounds), and a decision on `NoteViewSet`'s
   already-public `list`/`retrieve`.
6. ✅ **Cache-Tag headers (6)** — reinstated (available on Business as of
   2025-04-01, not Enterprise-only as an earlier revision assumed) and
   **shipped as part of (5)**: `DocumentViewSet.retrieve` emits `doc-{id}` and
   the purge path targets that tag, so one purge reaches every `?expand=…` and
   per-`Origin` variant. Remaining optional polish: tag `NoteViewSet` responses
   `doc-{document_id}` and add `project-{n}`/`org-{n}` tags for bulk
   invalidation — deferrable, not required by (4)/(5).

Then, as a **separate project**: make the frontend agree with whatever the
API settles on — matching tier boundaries for the HTML it serves, and
matching invalidation on edit. Sequenced after the above deliberately, so
the frontend has one stable contract to target instead of a moving one.

The zone-tier prerequisite is now answered: **Business, and `Cache-Tag`
purge _is_ available** (corrected 2026-07-30 — it went to all plans on
2025-04-01). The remaining open item is the per-`Origin` hit rate, which
bears on (4) rather than (5) — it determines whether long TTLs pay off at
all. It's no longer a purge-correctness prerequisite, though: tag purge
clears all `Vary` variants at once (see 4), so fixing `Vary: Origin` is now
an efficiency optimization, not a blocker.

The original "no schema migrations" estimate was wrong: step 2 required
two (`Section` and `Organization` timestamps). Authenticated traffic is
still unaffected throughout.

## Risks / things to verify

- **Authenticated bypass intact.** ✅ `anonymous_cache_control`
  (`decorators.py:34-36`) returns `private, no-cache` (not `no-store`, as
  originally written here) when `request.auth is not None` or
  `request.user.is_authenticated`. Covered by `test_retrieve_auth`. The
  decorator-collision theory this bullet referenced was ruled out — see
  (1). Re-verify when (4) starts setting `Cache-Control` in the view
  body, since that's the branch the decorator would no longer own.
- **Privacy flips fire quickly.** `_update_access` from `public` →
  `private` must purge or visitors keep seeing the public copy via CDN.
  This is _the_ reason to ship (5) before extending TTLs in (4). Note
  `invalidate_cache()` currently gets this backwards — see (5b).
- ~~**Slug changes.**~~ Retired — no slug mutation path exists (see
  Decisions, item 6, and 5c). Re-open only if a rename feature is added.
- **`AutoLastModifiedField` mutation paths.** Two confirmed gaps, both
  relevant to tier-by-`updated_at` in (4):
  - `update_access` (`tasks.py:270`) applies the final public flip with a
    queryset `Document.objects.filter(pk=…).update(...)`. That bypasses `save()`, so
    `AutoLastModifiedField` does **not** fire — `access` and
    `publication_date` change without bumping `updated_at`. In practice
    `_update_access` does a `document.save()` moments earlier so the
    timestamp is close, but the fields that actually changed aren't the
    ones that moved it.
  - The purge task bumps `updated_at` when it shouldn't — see the last
    subsection of (5).
- **Cloudflare Cache Rule precedence.** Partly resolved: as of 2026-07-20
  the rule no longer appends `no-store` and origin responses are being
  cached (`cf-cache-status: HIT`) — see (1). Still unverified is whether
  the rule sets its own edge TTL, which would override the per-tier
  `s-maxage` from (4) and make the whole tier table a no-op at the edge.
  Confirm in the dashboard before shipping (4). The synthetic
  `Last-Modified` question is now answered: the edge no longer overrides a
  real one, but it still fabricates one when the origin sends none — see
  the fail-safe subsection of (3).
- **⚠️ `Vary: Origin` fragments the cache without bound.** Confirmed
  2026-07-30, and worse than a "worth measuring" item. Current `Vary` is
  `Accept, Origin, Accept-Language` — (2) removed only `Cookie`. `Origin`
  comes from `CorsMiddleware`, and the response **reflects the requesting
  origin back** in `Access-Control-Allow-Origin`:

  ```
  Origin: https://www.documentcloud.org  → ACAO: https://www.documentcloud.org, MISS
  Origin: https://evil.example.com       → ACAO: https://evil.example.com,      MISS
  ```

  Both MISS while the no-`Origin` request HITs, so each distinct `Origin`
  is a separate cache entry and the key space is unbounded — any third
  party can mint fresh entries at will.

  Refined 2026-07-30: this is **fragmentation, not bypass.** Four
  sequential requests with the _same_ `Origin` went MISS → HIT → HIT → HIT,
  so CORS responses are cacheable; each origin just pays its own cold
  start. Less alarming than it first looked. It still dilutes (4) — a 30-day
  `s-maxage` is worth little at a low hit rate — so measure the real
  per-`Origin` hit rate before investing in the tier table. It is **no
  longer a purge problem**, though: with `Cache-Tag` available on Business
  (6, corrected), a single `doc-{id}` purge clears every `Origin` variant
  at once, so the fragmentation no longer multiplies unreachable URLs. Two
  ways to fix the dilution; the choice is a product decision, not just a
  caching one:
  - **Normalize the cache key at Cloudflare** to ignore `Origin` for this
    route. No API behavior change, so nothing breaks for existing clients.
    Preferred.
  - **Restrict CORS to a fixed allowlist** so ACAO is a constant. Cleaner
    at the origin, but this is a **breaking change for third-party browser
    clients** — anyone calling the public API from their own page loses
    access. Given a public documents API, that's a deliberate policy call
    and shouldn't be made incidentally in a caching PR.

- **`Vary: Accept` and `Accept-Language`.** `Accept` splits DRF's JSON vs
  browsable-API renderings (legitimate, but scrapers sending odd `Accept`
  values get their own entries); `Accept-Language` comes from
  `LocaleMiddleware` (`base.py:171`) and is pure fragmentation unless the
  API response is actually localized. Cheap to check, cheap to drop.
