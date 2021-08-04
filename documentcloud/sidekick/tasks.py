# Django
from celery.task import task
from django.conf import settings
from django.db import transaction

# Standard Library
import logging
import sys
from itertools import combinations

# Third Party
from requests.exceptions import RequestException

# DocumentCloud
from documentcloud.common.environment import httpsub
from documentcloud.documents.models import Document
from documentcloud.documents.tasks import solr_index_batch
from documentcloud.sidekick import lego
from documentcloud.sidekick.choices import Status
from documentcloud.sidekick.models import Sidekick

logger = logging.getLogger(__name__)

if settings.ENVIRONMENT.startswith("local"):
    # pylint: disable=unused-import
    from documentcloud.sidekick.local_tasks import sidekick_preprocess


def _httpsub_submit(url, project_pk, json, task_):
    """Helper to reliably submit a task to lambda via HTTP"""
    logger.info(
        "Submitting project %s for %s.  Retry: %d",
        project_pk,
        task_.name,
        task_.request.retries,
    )
    try:
        response = httpsub.post(url, json=json)
        response.raise_for_status()
        logger.info("Submitted project %s for %s succesfully.", project_pk, task_.name)
    except RequestException as exc:
        if task_.request.retries >= task_.max_retries:
            Sidekick.objects.filter(project_id=project_pk).update(status=Status.error)
            logger.error(
                "Submitting project %s for %s failed: %s",
                project_pk,
                task_.name,
                exc,
                exc_info=sys.exc_info(),
            )
        else:
            raise


@task(
    autoretry_for=(RequestException,),
    retry_backoff=30,
    retry_kwargs={"max_retries": settings.HTTPSUB_RETRY_LIMIT},
)
def preprocess(project_pk):
    """Start the sidekick pre-processing"""
    _httpsub_submit(
        settings.SIDEKICK_PROCESSING_URL,
        project_pk,
        {"project_id": project_pk},
        preprocess,
    )


@task
def lego_learn(sidekick_id, tag_name):
    """Start the lego learning"""

    logger.info("[LEGO LEARN] %s %s", sidekick_id, tag_name)

    try:
        sidekick = Sidekick.objects.get(pk=sidekick_id)
    except Sidekick.DoesNotExist:
        logger.warning("Sidekick does not exist: %s", sidekick_id)
        return

    if sidekick.status != Status.success:
        logger.warning(
            "Sidekick not in successful state: %s %s", sidekick_id, sidekick.status
        )

    try:
        doc_vectors, doc_ids = sidekick.get_document_vectors()
    except ValueError:
        sidekick.status = Status.error
        sidekick.save()
        return

    doc_ids = list(doc_ids)

    positive_docs = sidekick.project.documents.filter(
        data__contains={tag_name: ["true"]}, pk__in=doc_ids
    ).values_list("pk", flat=True)
    negative_docs = sidekick.project.documents.filter(
        data__contains={tag_name: ["false"]}, pk__in=doc_ids
    ).values_list("pk", flat=True)

    positive_doc_indices = [doc_ids.index(d) for d in positive_docs]
    negative_doc_indices = [doc_ids.index(d) for d in negative_docs]

    logger.info(
        "[LEGO LEARN] positive: %d negative: %d",
        len(positive_doc_indices),
        len(negative_doc_indices),
    )

    logger.info("[LEGO LEARN] positive: %s", positive_doc_indices)

    # constraints
    # list of triples of the form (id0, id1, constraint)
    # where constraint is 1 if both id0 and id1 are positive docs (positively correlated)
    # and constraint is 0 is one is positive and one is negative (negatively correlated)
    constraints = []
    for doc0, doc1 in combinations(positive_doc_indices, 2):
        constraints.append((doc0, doc1, 1))
    for doc0 in positive_doc_indices:
        for doc1 in negative_doc_indices:
            constraints.append((doc0, doc1, 0))

    logger.info("[LEGO LEARN] constraints: %s", constraints)

    # percentiles
    # list of percentiles corresponding to document index
    dists, percentiles = lego.lego_learn(doc_vectors, constraints, positive_doc_indices)

    logger.info("[LEGO LEARN] dists: %s", dists)
    logger.info("[LEGO LEARN] percentiles: %s", percentiles)

    documents = Document.objects.in_bulk(doc_ids)
    for doc_id, dist in zip(doc_ids, dists):
        documents[doc_id].data[f"{tag_name}_score"] = [dist]
        documents[doc_id].solr_dirty = True
    with transaction.atomic():
        Document.objects.bulk_update(documents.values(), ["data", "solr_dirty"])
        transaction.on_commit(
            lambda: solr_index_batch.delay(
                [doc_ids], field_updates={f"data_{tag_name}_score": "set"}
            )
        )
