#!/usr/bin/env python3
"""
solr_benchmark.py — capture a point-in-time performance snapshot of the
DocumentCloud SolrCloud cluster for the health-assessment roadmap.

It reads Solr's own metrics API (safe on production — passive, read-only) and
records the scorecard from runbook 13:

  * per-handler query latency percentiles (p50/p95/p99), request rate,
    errors, timeouts, serverErrors
  * cache hit ratios + evictions + size (filterCache / queryResultCache /
    documentCache), both lifetime-cumulative and current-searcher
  * index size on disk, numDocs, searcher warmup time
  * JVM heap used/max and GC counts/times (per collector, auto-discovered)
  * OS-level free physical memory, load average, open file descriptors
  * container filesystem usable/total space
  * core start time (so you can tell when counters were reset by a restart)
  * cluster health (replica states per collection)
  * (optional) a light client-side latency probe

IMPORTANT — two scorecard rows this script CANNOT provide, by design:

  * "OS page cache size" (`free -g` buff/cache). The JVM only exposes
    os.freePhysicalMemorySize, which is MemFree — the `free` *"free"* column,
    not "buff/cache". As page cache warms correctly MemFree goes DOWN, so it is
    not a substitute. Capture `free -g` per node separately.
  * EBS/CloudWatch counters, GC *pause* distributions (parse solr_gc.log), OOM
    counts, and max sustainable QPS (load test).

Counters are cumulative since core/JVM start: count, errors, timeouts, GC
counts/times and the cumulative_* cache stats all reset when Solr restarts —
which every heap/instance change does. Compare DELTAS between two runs with the
same core_start_time; across a restart, compare rates and current_* instead.

By default a run emits its JSON snapshot to STDOUT and writes no files, because
the primary way this runs is on a Heroku dyno, whose filesystem is wiped on
cycle. Capture it locally and build the CSV scorecards from the captures:

    heroku run --no-tty --app <app> \
      "python scripts/solr_benchmark.py --hosts h1:7377,h2:7377,h3:7377 \
         --label baseline" > benchmarks/baseline.json
    ./solr_benchmark.py --ingest benchmarks/*.json --outdir benchmarks

Pass --label to tag the run ("baseline", "after-heap-14g") so a baseline and
every later run accumulate in one scorecard. Where the filesystem persists,
--no-stdout writes the JSON snapshot + CSVs directly under --outdir.

AUTH IS READ FROM THE ENVIRONMENT — never pass the password on the command line.
It uses the DocumentCloud app's own config vars (config/settings/base.py), so it
works unchanged under `heroku run` (which inherits the app's config vars):

    SOLR_USERNAME / SOLR_PASSWORD   # the app's Solr credential (preferred)
    SOLR_HOST_URL                   # used if --hosts/SOLR_HOSTS not given
    SOLR_SEARCH_HANDLER             # default for --handler
    SOLR_COLLECTION_NAME            # default for --collection
    SOLR_VERIFY                     # "False" disables TLS verify; else cert body

For manual runs you can instead export SOLR_AUTH='user:password' (and SOLR_HOSTS
/ SOLR_CA). Nothing sensitive is ever printed or written.

Usage (manual run from a laptop/bastion that can reach the nodes):
    export SOLR_AUTH='solr:...'
    ./solr_benchmark.py \
        --hosts ec2-18-206-129-164.compute-1.amazonaws.com:7377,\
ec2-54-205-197-205.compute-1.amazonaws.com:7377,\
ec2-18-215-134-28.compute-1.amazonaws.com:7377 \
        --label baseline --insecure > baseline.json

Exit codes: 0 = all good; 1 = reachable but unhealthy (a replica is not active,
or cluster state could not be read); 2 = a node could not be scraped; 3 =
--ingest parsed nothing. Usable as a health check.

Only depends on the Python 3 standard library.
"""

# Standard Library
import argparse
import atexit
import base64
import contextlib
import csv
import datetime
import json
import math
import os
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_HANDLER = "/mainsearch"
DEFAULT_COLLECTION = "documentcloud"
CACHES = ("filterCache", "queryResultCache", "documentCache")
CACHE_SUFFIXES = ("hitratio", "hitratio_cur", "evictions", "evictions_cur", "size")

EXIT_OK = 0
EXIT_UNHEALTHY = 1
EXIT_FETCH_ERROR = 2
EXIT_NOTHING_INGESTED = 3

# HTTP statuses where retrying is pointless (auth/URL problems, not transient).
NO_RETRY_STATUS = frozenset({400, 401, 403, 404, 405})

# CSV scorecard columns (shared by the live run and by --ingest).
QUERY_FIELDS = [
    "timestamp",
    "label",
    "host",
    "core",
    "core_start_time",
    "count",
    "meanRate",
    "p50_ms",
    "p95_ms",
    "p99_ms",
    "p999_ms",
    "max_ms",
    "errors",
    "timeouts",
    "serverErrors",
    "index_size_bytes",
    "num_docs",
    "max_doc",
    "warmup_ms",
] + [f"{cache}_{suffix}" for cache in CACHES for suffix in CACHE_SUFFIXES]
HOST_FIELDS = [
    "timestamp",
    "label",
    "host",
    "heap_used_bytes",
    "heap_max_bytes",
    "heap_used_pct",
    "gc_total_count",
    "gc_total_ms",
    "gc_young_count",
    "gc_young_ms",
    "gc_old_count",
    "gc_old_ms",
    "os_free_phys_bytes",
    "os_total_phys_bytes",
    "os_load_avg",
    "os_open_fds",
    "os_cpu_load",
    "fs_usable_bytes",
    "fs_total_bytes",
]
CLUSTER_FIELDS = [
    "timestamp",
    "label",
    "collection",
    "shards",
    "replicas",
    "active",
    "not_active",
    "states",
]

# Metrics we expect on every healthy node. Anything missing is reported rather
# than silently written as null — a null here means the key name is wrong for
# this Solr/JVM version, not that the cluster is idle.
EXPECTED_CORE_KEYS = ("count", "p95_ms", "index_size_bytes", "num_docs")
EXPECTED_JVM_KEYS = ("heap_used_bytes", "gc_total_count", "os_free_phys_bytes")


def eprint(*args, **kwargs):
    """print() to stderr — for diagnostics that must not pollute stdout."""
    kwargs["file"] = sys.stderr
    print(*args, **kwargs)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def get_auth_header():
    """Build a Basic auth header from the environment. Never logged.

    Prefers the DocumentCloud app's own config vars (SOLR_USERNAME /
    SOLR_PASSWORD, per config/settings/base.py) so this works unchanged under
    `heroku run`, which inherits the app's config vars. SOLR_AUTH (user:pass)
    and SOLR_USER are accepted as convenience aliases for manual runs."""
    auth = os.environ.get("SOLR_AUTH")
    if not auth:
        user = os.environ.get("SOLR_USERNAME") or os.environ.get("SOLR_USER")
        pw = os.environ.get("SOLR_PASSWORD") or os.environ.get("SOLR_PASS")
        # base.py only sets auth when BOTH are non-empty; mirror that.
        if user and pw:
            auth = f"{user}:{pw}"
    if not auth:
        return None
    token = base64.b64encode(auth.encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def make_ssl_context(insecure, ca_file):
    ctx = ssl.create_default_context()
    if ca_file:
        ctx.load_verify_locations(ca_file)
    elif insecure:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def http_get_json(url, auth_header, ctx, timeout, retries=0, backoff=1.0):
    """GET + parse JSON, retrying transient failures.

    A single timeout against a struggling cluster would otherwise drop that
    node's row and leave a silent hole in the baseline CSV."""
    attempt = 0
    while True:
        req = urllib.request.Request(url)
        if auth_header:
            req.add_header("Authorization", auth_header)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as e:
            fatal = isinstance(e, urllib.error.HTTPError) and e.code in NO_RETRY_STATUS
            if fatal or attempt >= retries:
                raise
            attempt += 1
            eprint(f"  retry {attempt}/{retries} after {type(e).__name__}: {e}")
            time.sleep(backoff * attempt)


def percentile(values, p):
    """Nearest-rank percentile of an unsorted list of numbers."""
    if not values:
        return None
    s = sorted(values)
    k = max(0, math.ceil(p / 100.0 * len(s)) - 1)
    return s[k]


def base_url(host):
    """Normalize a host[:port] into an https base URL (default port 7377)."""
    host = host.strip()
    if host.startswith("http://") or host.startswith("https://"):
        return host.rstrip("/")
    if ":" not in host:
        host = f"{host}:7377"
    return f"https://{host}"


def fmt(value, spec=""):
    """None-safe format() — renders missing metrics as '?' instead of raising."""
    if value is None:
        return "?"
    try:
        return format(value, spec)
    except (TypeError, ValueError):
        return str(value)


# --------------------------------------------------------------------------- #
# Collection
# --------------------------------------------------------------------------- #
def fetch_metrics(host, auth_header, ctx, handler, timeout, retries=0):
    """Pull the core + jvm + node metrics we care about from one Solr node."""
    prefixes = ",".join(
        [
            f"QUERY.{handler}",
            "CACHE.searcher",
            "SEARCHER.searcher",
            "INDEX.sizeInBytes",
            "CORE.startTime",
            "CORE.sizeInBytes",
            "memory.heap",
            "gc",
            "os.",
            "CONTAINER.fs",
        ]
    )
    url = (
        f"{base_url(host)}/solr/admin/metrics"
        f"?group=core,jvm,node&prefix={urllib.parse.quote(prefixes)}&wt=json"
    )
    return http_get_json(url, auth_header, ctx, timeout, retries)


def parse_gc(data):
    """Sum GC counts/times across whatever collectors this JVM actually uses.

    Collector names vary (G1-Young-Generation, PS-Scavenge, ParNew,
    ConcurrentMarkSweep, ZGC...), so discover them instead of hardcoding G1 —
    a hardcoded name silently yields nulls on a differently-tuned JVM."""
    per_collector = {}
    for key, value in data.items():
        if not key.startswith("gc."):
            continue
        if key.endswith(".count"):
            name, field = key[3:-6], "count"
        elif key.endswith(".time"):
            name, field = key[3:-5], "time"
        else:
            continue
        per_collector.setdefault(name, {})[field] = value

    def total(names, field):
        vals = [
            per_collector[n].get(field)
            for n in names
            if per_collector[n].get(field) is not None
        ]
        return sum(vals) if vals else None

    all_names = list(per_collector)
    young = [
        n
        for n in all_names
        if any(t in n.lower() for t in ("young", "scavenge", "parnew", "copy", "eden"))
    ]
    old = [
        n
        for n in all_names
        if any(
            t in n.lower() for t in ("old", "marksweep", "tenured", "global", "major")
        )
    ]
    return {
        "gc_per_collector": per_collector,
        "gc_total_count": total(all_names, "count"),
        "gc_total_ms": total(all_names, "time"),
        "gc_young_count": total(young, "count"),
        "gc_young_ms": total(young, "time"),
        "gc_old_count": total(old, "count"),
        "gc_old_ms": total(old, "time"),
    }


def parse_node_metrics(raw, handler):
    """Turn one node's raw metrics JSON into tidy per-core + jvm rows."""
    metrics = raw.get("metrics", {})
    cores = []
    jvm = {}
    node_fs = {}
    for registry, data in metrics.items():
        if registry.startswith("solr.core."):
            rt = data.get(f"QUERY.{handler}.requestTimes", {})
            searcher = data.get("SEARCHER.searcher.numDocs")
            row = {
                "core": registry.replace("solr.core.", ""),
                "core_start_time": data.get("CORE.startTime"),
                "count": rt.get("count"),
                "meanRate": rt.get("meanRate"),
                "p50_ms": rt.get("median_ms"),
                "p95_ms": rt.get("p95_ms"),
                "p99_ms": rt.get("p99_ms"),
                "p999_ms": rt.get("p999_ms"),
                "max_ms": rt.get("max_ms"),
                "errors": data.get(f"QUERY.{handler}.errors", {}).get("count"),
                "timeouts": data.get(f"QUERY.{handler}.timeouts", {}).get("count"),
                "serverErrors": data.get(f"QUERY.{handler}.serverErrors", {}).get(
                    "count"
                ),
                "index_size_bytes": data.get("INDEX.sizeInBytes")
                or data.get("CORE.sizeInBytes"),
                "num_docs": searcher,
                "max_doc": data.get("SEARCHER.searcher.maxDoc"),
                "warmup_ms": data.get("SEARCHER.searcher.warmupTime"),
            }
            for cache in CACHES:
                c = data.get(f"CACHE.searcher.{cache}", {})
                # Record BOTH: cumulative is lifetime-since-core-start (resets on
                # restart), current is this searcher only. Comparing a weeks-old
                # cumulative ratio against a freshly restarted one is meaningless,
                # so runbook 07 needs the pair.
                row[f"{cache}_hitratio"] = c.get("cumulative_hitratio")
                row[f"{cache}_hitratio_cur"] = c.get("hitratio")
                row[f"{cache}_evictions"] = c.get("cumulative_evictions")
                row[f"{cache}_evictions_cur"] = c.get("evictions")
                row[f"{cache}_size"] = c.get("size")
            row["missing"] = [k for k in EXPECTED_CORE_KEYS if row.get(k) is None]
            cores.append(row)
        elif registry == "solr.jvm":
            heap_used = data.get("memory.heap.used")
            heap_max = data.get("memory.heap.max")
            jvm = {
                "heap_used_bytes": heap_used,
                "heap_max_bytes": heap_max,
                "heap_used_pct": (
                    round(100.0 * heap_used / heap_max, 1)
                    if heap_used and heap_max
                    else None
                ),
                # NOTE: freePhysicalMemorySize is MemFree, NOT page cache
                # (buff/cache). See the module docstring.
                "os_free_phys_bytes": data.get("os.freePhysicalMemorySize"),
                "os_total_phys_bytes": data.get("os.totalPhysicalMemorySize"),
                "os_load_avg": data.get("os.systemLoadAverage"),
                "os_open_fds": data.get("os.openFileDescriptorCount"),
                "os_cpu_load": data.get("os.processCpuLoad"),
            }
            jvm.update(parse_gc(data))
            jvm["missing"] = [k for k in EXPECTED_JVM_KEYS if jvm.get(k) is None]
        elif registry == "solr.node":
            node_fs = {
                "fs_usable_bytes": data.get("CONTAINER.fs.usableSpace"),
                "fs_total_bytes": data.get("CONTAINER.fs.totalSpace"),
            }
    if jvm:
        jvm.update(node_fs)
    return cores, jvm


def fetch_cluster_health(host, auth_header, ctx, timeout, retries=0):
    """Count replica states per collection via CLUSTERSTATUS."""
    url = f"{base_url(host)}/solr/admin/collections" f"?action=CLUSTERSTATUS&wt=json"
    raw = http_get_json(url, auth_header, ctx, timeout, retries)
    out = {"collections": {}, "aliases": raw.get("cluster", {}).get("aliases", {})}
    collections = raw.get("cluster", {}).get("collections", {})
    for cname, cdata in collections.items():
        states = {}
        replicas = 0
        for shard in cdata.get("shards", {}).values():
            for rep in shard.get("replicas", {}).values():
                replicas += 1
                st = rep.get("state", "unknown")
                states[st] = states.get(st, 0) + 1
        out["collections"][cname] = {
            "shards": len(cdata.get("shards", {})),
            "replicas": replicas,
            "states": states,
        }
    return out


def probe_latency(host, auth_header, ctx, collection, query, count, timeout):
    """Optional: measure client-side latency of N sequential canary queries.

    OFF by default (count=0). Keep counts low on production; this actively
    loads Solr. Prefer running against staging (see runbook 13). Note that
    nearest-rank p95/p99 over a handful of samples is just the max — use a real
    load tool (vegeta/k6) for trustworthy client-side tails."""
    if count <= 0:
        return None
    url = (
        f"{base_url(host)}/solr/{collection}/select"
        f"?q={urllib.parse.quote(query)}&rows=10&wt=json"
    )
    latencies = []
    errors = 0
    for _ in range(count):
        t0 = time.perf_counter()
        try:
            http_get_json(url, auth_header, ctx, timeout)
            latencies.append((time.perf_counter() - t0) * 1000.0)
        except (urllib.error.URLError, OSError, ValueError):
            errors += 1
        time.sleep(0.05)  # be gentle
    return {
        "count": count,
        "errors": errors,
        "p50_ms": percentile(latencies, 50),
        "p95_ms": percentile(latencies, 95),
        "p99_ms": percentile(latencies, 99),
        "max_ms": max(latencies) if latencies else None,
    }


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def append_csv(path, fieldnames, rows):
    if not rows:
        return
    exists = os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def human_bytes(n):
    if n is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}PB"


def print_summary(snapshot):
    print(
        f"\n=== Solr benchmark snapshot: {snapshot['label']} "
        f"@ {snapshot['timestamp']} ==="
    )
    for node in snapshot["nodes"]:
        host = node["host"]
        if node.get("error"):
            print(f"\n[{host}] ERROR: {node['error']}")
            continue
        jvm = node.get("jvm", {})
        print(f"\n[{host}]")
        if jvm:
            print(
                f"  heap {human_bytes(jvm.get('heap_used_bytes'))}/"
                f"{human_bytes(jvm.get('heap_max_bytes'))} "
                f"({fmt(jvm.get('heap_used_pct'))}%)  "
                f"MemFree {human_bytes(jvm.get('os_free_phys_bytes'))}  "
                f"load {fmt(jvm.get('os_load_avg'))}  "
                f"fds {fmt(jvm.get('os_open_fds'))}"
            )
            print(
                f"  gc total {fmt(jvm.get('gc_total_ms'))}ms/"
                f"{fmt(jvm.get('gc_total_count'))}  "
                f"old {fmt(jvm.get('gc_old_ms'))}ms/{fmt(jvm.get('gc_old_count'))}  "
                f"disk free {human_bytes(jvm.get('fs_usable_bytes'))}/"
                f"{human_bytes(jvm.get('fs_total_bytes'))}"
            )
        for c in node.get("cores", []):
            print(
                f"  {c['core']}: "
                f"p50={fmt(c['p50_ms'])} p95={fmt(c['p95_ms'])} "
                f"p99={fmt(c['p99_ms'])} ms  "
                f"n={fmt(c['count'])} rate={fmt(c.get('meanRate'), '.3f')}/s"
            )
            print(
                f"      err={fmt(c['errors'])} timeouts={fmt(c['timeouts'])} "
                f"5xx={fmt(c.get('serverErrors'))}  "
                f"index={human_bytes(c.get('index_size_bytes'))} "
                f"docs={fmt(c.get('num_docs'))} "
                f"warmup={fmt(c.get('warmup_ms'))}ms"
            )
            print(
                f"      filterHit={fmt(c.get('filterCache_hitratio'))} "
                f"(cur {fmt(c.get('filterCache_hitratio_cur'))}, "
                f"evict {fmt(c.get('filterCache_evictions'))})  "
                f"qrHit={fmt(c.get('queryResultCache_hitratio'))}  "
                f"docHit={fmt(c.get('documentCache_hitratio'))}"
            )
        if node.get("probe"):
            p = node["probe"]
            print(
                f"  probe: p50={fmt(p['p50_ms'], '.0f')} "
                f"p95={fmt(p['p95_ms'], '.0f')} p99={fmt(p['p99_ms'], '.0f')} ms "
                f"(n={p['count']}, err={p['errors']})"
            )
        missing = sorted(
            {m for c in node.get("cores", []) for m in c.get("missing", [])}
            | set(jvm.get("missing", []))
        )
        if missing:
            print(
                f"  !! metrics absent (wrong key for this Solr/JVM version?): "
                f"{', '.join(missing)}"
            )
    ch = snapshot.get("cluster_health", {})
    if ch.get("error"):
        print(f"\n[cluster] ERROR: {ch['error']} — replica states UNKNOWN")
    elif ch:
        print("\n[cluster]")
        for cname, c in ch.get("collections", {}).items():
            print(
                f"  {cname}: {c['shards']} shards, {c['replicas']} replicas, "
                f"states={c['states']}"
            )
        not_active = sum(
            n
            for c in ch.get("collections", {}).values()
            for st, n in c["states"].items()
            if st != "active"
        )
        if not_active:
            print(f"  *** {not_active} replica(s) NOT active ***")
    print()


def snapshot_to_rows(snapshot):
    """Flatten one snapshot into (query, host, cluster) CSV row lists."""
    ts = snapshot.get("timestamp")
    label = snapshot.get("label")
    query_rows, host_rows, cluster_rows = [], [], []
    for node in snapshot.get("nodes", []):
        if node.get("error"):
            continue
        for c in node.get("cores", []):
            query_rows.append(
                {"timestamp": ts, "label": label, "host": node["host"], **c}
            )
        jvm = node.get("jvm", {})
        if jvm:
            host_rows.append(
                {"timestamp": ts, "label": label, "host": node["host"], **jvm}
            )
    ch = snapshot.get("cluster_health", {})
    for cname, c in ch.get("collections", {}).items():
        cluster_rows.append(
            {
                "timestamp": ts,
                "label": label,
                "collection": cname,
                "shards": c["shards"],
                "replicas": c["replicas"],
                "active": c["states"].get("active", 0),
                "not_active": sum(n for st, n in c["states"].items() if st != "active"),
                "states": json.dumps(c["states"]),
            }
        )
    return query_rows, host_rows, cluster_rows


def write_scorecards(outdir, query_rows, host_rows, cluster_rows):
    """Append the three CSV scorecards under outdir."""
    os.makedirs(outdir, exist_ok=True)
    append_csv(os.path.join(outdir, "scorecard_query.csv"), QUERY_FIELDS, query_rows)
    append_csv(os.path.join(outdir, "scorecard_host.csv"), HOST_FIELDS, host_rows)
    append_csv(
        os.path.join(outdir, "scorecard_cluster.csv"), CLUSTER_FIELDS, cluster_rows
    )


def snapshot_exit_code(snapshot):
    """0 = healthy, 1 = unhealthy/unknown, 2 = a node could not be scraped."""
    if any(n.get("error") for n in snapshot.get("nodes", [])):
        return EXIT_FETCH_ERROR
    ch = snapshot.get("cluster_health", {})
    if ch.get("error") or not ch.get("collections"):
        # Could not read cluster state — absence of evidence is not health.
        return EXIT_UNHEALTHY
    if any(
        st != "active" and n
        for c in ch["collections"].values()
        for st, n in c.get("states", {}).items()
    ):
        return EXIT_UNHEALTHY
    return EXIT_OK


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def run_ingest(ap, args):
    """Local mode: build CSVs from previously captured JSON snapshots."""
    if not args.ingest:
        ap.error("--ingest needs one or more snapshot JSON files")
    q_rows, h_rows, c_rows = [], [], []
    ok, failed = 0, []
    for path in args.ingest:
        try:
            with open(path) as f:
                snap = json.load(f)
        except (OSError, ValueError) as e:
            eprint(f"skipping {path}: {e}")
            failed.append(path)
            continue
        qi, hi, ci = snapshot_to_rows(snap)
        q_rows += qi
        h_rows += hi
        c_rows += ci
        ok += 1
    if not ok:
        eprint(
            f"ERROR: ingested nothing — all {len(args.ingest)} file(s) failed to "
            f"parse. (A truncated `heroku run` capture is the usual cause.)"
        )
        return EXIT_NOTHING_INGESTED
    write_scorecards(args.outdir, q_rows, h_rows, c_rows)
    eprint(
        f"Ingested {ok}/{len(args.ingest)} snapshot(s) → "
        f"{len(q_rows)} query / {len(h_rows)} host / {len(c_rows)} cluster row(s) "
        f"in {args.outdir}/"
    )
    if failed:
        eprint(f"Failed to parse: {', '.join(failed)}")
        return EXIT_FETCH_ERROR
    if not (q_rows or h_rows or c_rows):
        # Parsed fine but every node in every snapshot had errored at capture
        # time — writing nothing while reporting success would hide that.
        eprint(
            "ERROR: snapshots parsed but contained no usable rows (every node "
            "errored at capture time). Check auth/reachability and re-capture."
        )
        return EXIT_FETCH_ERROR
    return EXIT_OK


def _unlink_quietly(path):
    with contextlib.suppress(OSError):
        os.unlink(path)


def resolve_tls(args):
    """--insecure / SOLR_CA win; otherwise mirror the app's SOLR_VERIFY."""
    ca_file = os.environ.get("SOLR_CA")
    insecure = args.insecure
    solr_verify = os.environ.get("SOLR_VERIFY")
    if not ca_file and not insecure and solr_verify is not None:
        if solr_verify.strip() == "False":
            insecure = True
        elif solr_verify.strip():
            # Cert *contents* in the env var: stage them in a temp file and use
            # it as the CA bundle. Clean up on exit so repeated runs (e.g. a
            # cron) don't litter /tmp with .pem files.
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
            tf.write(solr_verify.encode("ascii"))
            tf.close()
            ca_file = tf.name
            atexit.register(_unlink_quietly, ca_file)
    if insecure and not ca_file:
        eprint(
            "note: --insecure sends Basic credentials over an unverified TLS "
            "connection. Prefer SOLR_VERIFY/SOLR_CA where available."
        )
    return make_ssl_context(insecure, ca_file)


def main():
    ap = argparse.ArgumentParser(
        description="Capture a Solr performance/health snapshot for the "
        "health-assessment scorecard.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument(
        "--hosts",
        default=os.environ.get("SOLR_HOSTS", ""),
        help="Comma-separated host[:port] list (or set SOLR_HOSTS). Default "
        "port 7377, https. If unset, falls back to the app's SOLR_HOST_URL "
        "(the load balancer).",
    )
    ap.add_argument(
        "--handler",
        default=os.environ.get("SOLR_SEARCH_HANDLER", DEFAULT_HANDLER),
        help="Request handler to read latency from "
        "(defaults to $SOLR_SEARCH_HANDLER or /mainsearch).",
    )
    ap.add_argument(
        "--collection",
        default=os.environ.get("SOLR_COLLECTION_NAME", DEFAULT_COLLECTION),
        help="Collection/alias for the optional --probe-count latency probe. "
        "Cluster health always covers every collection.",
    )
    ap.add_argument(
        "--label",
        default="unlabeled",
        help='Tag for this run, e.g. "baseline" or "after-heap-14g".',
    )
    ap.add_argument(
        "--outdir",
        default="benchmarks",
        help="Directory for JSON snapshots + CSV scorecards.",
    )
    ap.add_argument(
        "--timeout", type=float, default=15.0, help="Per-request timeout (seconds)."
    )
    ap.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Retries after a transient failure, per request. Prevents one "
        "timeout from leaving a hole in the scorecard.",
    )
    ap.add_argument(
        "--insecure",
        action="store_true",
        help="Skip TLS verification (self-signed cert). "
        "Or set SOLR_CA to a CA bundle instead.",
    )
    ap.add_argument(
        "--probe-query",
        default="*:*",
        help="Query for the optional client-side latency probe.",
    )
    ap.add_argument(
        "--probe-count",
        type=int,
        default=0,
        help="Number of probe requests per host (0 = disabled). "
        "Actively loads Solr — keep low; prefer staging.",
    )
    ap.add_argument(
        "--stdout",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Emit the JSON snapshot to stdout (and nothing else there); write "
        "no files. The default, because the primary run is on an ephemeral host "
        "(a Heroku dyno) captured locally: "
        "`heroku run --no-tty '...' > run.json`, then --ingest it. "
        "Pass --no-stdout to write the JSON + CSV scorecards under --outdir "
        "instead (only useful where the filesystem persists).",
    )
    ap.add_argument(
        "--ingest",
        nargs="*",
        metavar="SNAPSHOT.json",
        help="Local mode: read one or more captured JSON snapshots and append "
        "them to the CSV scorecards in --outdir, then exit. No cluster access "
        "needed. Pairs with the default stdout captures.",
    )
    args = ap.parse_args()

    if args.ingest is not None:
        return run_ingest(ap, args)

    # A handler without its leading slash would silently match no metrics.
    handler = args.handler if args.handler.startswith("/") else f"/{args.handler}"

    hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
    if not hosts:
        # Fall back to the app's SOLR_HOST_URL (the load balancer). This gives
        # one node per call (whichever the LB picks), not per-node metrics —
        # pass --hosts with the individual node names for a full picture.
        host_url = os.environ.get("SOLR_HOST_URL")
        if host_url:
            hosts = [host_url]
            eprint(
                "note: no --hosts/SOLR_HOSTS; using SOLR_HOST_URL "
                "(load balancer — one node per call). Pass --hosts with the "
                "individual node hostnames for per-node metrics."
            )
    if not hosts:
        ap.error("no hosts given (use --hosts, or set SOLR_HOSTS / SOLR_HOST_URL)")

    auth_header = get_auth_header()
    if not auth_header:
        eprint(
            "WARNING: no auth found (set SOLR_USERNAME + SOLR_PASSWORD, "
            "or SOLR_AUTH=user:pass)"
        )

    ctx = resolve_tls(args)

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot = {
        "timestamp": ts,
        "label": args.label,
        "handler": handler,
        "nodes": [],
    }

    for host in hosts:
        node = {"host": host}
        try:
            raw = fetch_metrics(
                host, auth_header, ctx, handler, args.timeout, args.retries
            )
            cores, jvm = parse_node_metrics(raw, handler)
            node["cores"] = cores
            node["jvm"] = jvm
            node["probe"] = probe_latency(
                host,
                auth_header,
                ctx,
                args.collection,
                args.probe_query,
                args.probe_count,
                args.timeout,
            )
        except (urllib.error.URLError, OSError, ValueError) as e:
            node["error"] = str(e)
        snapshot["nodes"].append(node)

    # cluster health from the first host that answers
    snapshot["cluster_health"] = {"error": "no host answered"}
    for host in hosts:
        try:
            snapshot["cluster_health"] = fetch_cluster_health(
                host, auth_header, ctx, args.timeout, args.retries
            )
            break
        except (urllib.error.URLError, OSError, ValueError) as e:
            snapshot["cluster_health"] = {"error": str(e)}

    # --- output ---
    if args.stdout:
        # Ephemeral host (e.g. Heroku dyno): emit ONLY the JSON snapshot to
        # stdout so it can be captured locally; send the human summary and all
        # diagnostics to stderr so the redirect stays clean. Write no files.
        with contextlib.redirect_stdout(sys.stderr):
            print_summary(snapshot)
        json.dump(snapshot, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        json_path = os.path.join(args.outdir, f"{ts}_{args.label}.json")
        os.makedirs(args.outdir, exist_ok=True)
        with open(json_path, "w") as f:
            json.dump(snapshot, f, indent=2)
        write_scorecards(args.outdir, *snapshot_to_rows(snapshot))
        print_summary(snapshot)
        print(f"Wrote {json_path}")
        print(f"Appended CSV scorecards in {args.outdir}/")

    # Non-zero exit if anything is unhealthy, so it's usable in checks/CI.
    return snapshot_exit_code(snapshot)


if __name__ == "__main__":
    sys.exit(main())
