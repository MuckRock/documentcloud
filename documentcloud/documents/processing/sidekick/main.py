# Standard Library
import logging
import os
import re
from collections import Counter
from urllib.parse import urljoin

# Third Party
import environ
import numpy as np
import requests
import sklearn.decomposition
from sklearn.feature_extraction.text import TfidfVectorizer

env = environ.Env()
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Imports based on execution context
if env.str("ENVIRONMENT").startswith("local"):
    from documentcloud.common import path
    from documentcloud.common.environment import get_pubsub_data, publisher, storage
    from documentcloud.common.serverless import utils
    from documentcloud.common.serverless.error_handling import pubsub_function
else:
    from common import path
    from common.environment import get_pubsub_data, publisher, storage
    from common.serverless import utils
    from common.serverless.error_handling import pubsub_function

    # only initialize sentry on serverless
    # pylint: disable=import-error
    import sentry_sdk
    from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    # pylint: enable=import-error

    sentry_sdk.init(
        dsn=env("SENTRY_DSN"), integrations=[AwsLambdaIntegration(), RedisIntegration()]
    )

REDIS = utils.get_redis()
API_CALLBACK = env.str("API_CALLBACK")
PROCESSING_TOKEN = env.str("PROCESSING_TOKEN")
VOCAB_SIZE = env.int("VOCAB_SIZE", default=30000)
TOKEN_PATTERN = re.compile(r"(?u)\b\w\w+\b")
EMBEDDING_DIR = env.str("EMBEDDING_DIR", default="embedding")

SIDEKICK_PREPROCESS_TOPIC = publisher.topic_path(
    "documentcloud",
    env.str("SIDEKICK_PREPROCESS_TOPIC", default="sidekick-preprocess-topic"),
)

LANGUAGES = {"eng": "en"}


def send_sidekick_update(project_id, json):
    """Send an update to the API server for sidekick"""
    utils.request(REDIS, "patch", f"projects/{project_id}/sidekick/", json)


def load_documents(project_id):
    """Load the documents

    Fetch their IDs, slugs and languages via the API
    Use the ID and slug to fetch the text from S3
    Return the most common language among the documents as the language to use
      for the word embeddings
    """

    logger.info(
        "[SIDEKICK PREPROCESS] project_id: %s - fetching project documents", project_id
    )
    file_names = []
    languages = Counter()
    doc_ids = []
    next_ = urljoin(API_CALLBACK, f"projects/{project_id}/documents/?expand=document")

    while next_:
        response = requests.get(
            next_, headers={"Authorization": f"processing-token {PROCESSING_TOKEN}"}
        )
        response.raise_for_status()
        response_json = response.json()
        next_ = response_json["next"]
        for result in response_json["results"]:
            file_names.append(
                path.text_path(result["document"]["id"], result["document"]["slug"])
            )
            languages.update([result["document"]["language"]])
            doc_ids.append(result["document"]["id"])

    language = languages.most_common()[0][0]

    # download the files in parallel
    texts = storage.async_download(file_names)

    return texts, doc_ids, language


def process_text(project_id, texts):
    """Calculate the vocabulary for the corpus based on the document texts"""

    logger.info("[SIDEKICK PREPROCESS] project_id: %s - calculating vocab", project_id)

    logger.info("[SIDEKICK PREPROCESS] project_id: %s - tfidf", project_id)

    # Derive tf-idf data on corpus
    vectorizer = TfidfVectorizer(
        strip_accents="unicode", stop_words=None, max_features=VOCAB_SIZE
    )

    tfidf = vectorizer.fit_transform(texts)
    features = vectorizer.get_feature_names()

    logger.info("[SIDEKICK PREPROCESS] project_id: %s - svd", project_id)

    # Project tf-idf data down in dimensionality
    svd_transformer = sklearn.decomposition.TruncatedSVD(
        300, algorithm="randomized", n_iter=5
    )
    doc_svd = svd_transformer.fit_transform(tfidf)

    return tfidf, features, doc_svd


def doc_embedding(project_id, language, tfidf, features, doc_svd):
    """Calculate the doc embeddings"""
    import fasttext

    logger.info("[SIDEKICK PREPROCESS] project_id: %s - doc embeddings", project_id)

    # Load the embedding model
    # error if language not present
    language = LANGUAGES.get(language, language)
    model = fasttext.load_model(os.path.join(EMBEDDING_DIR, f"cc.{language}.300.bin"))
    embedding_vectors = np.array(
        [model.get_word_vector(feature) for feature in features]
    )

    # scale embedding vectors based on frequency of the words
    doc_embeddings = np.dot(tfidf.A, embedding_vectors)

    # Doc vectors are just doc_svd and doc_embeddings concatenated
    doc_vectors = np.hstack((doc_svd, doc_embeddings))

    # Serialize doc vectors to file
    with storage.open(
        path.sidekick_document_vectors_path(project_id), "wb"
    ) as vectors_file:
        np.savez_compressed(vectors_file, doc_vectors)


def doc_embedding_(project_id, _language, _tfidf, _features, doc_svd, doc_ids):
    """Simpler doc embeddings - skip word vectors and just use the doc svd"""

    logger.info("[SIDEKICK PREPROCESS] project_id: %s - doc embeddings", project_id)

    # Serialize doc vectors to file
    with storage.open(
        path.sidekick_document_vectors_path(project_id), "wb"
    ) as vectors_file:
        np.savez_compressed(vectors_file, vectors=doc_svd, ids=doc_ids)


@pubsub_function(REDIS, SIDEKICK_PREPROCESS_TOPIC)
def preprocess(data, _context=None):
    """Preprocess the documents in a project for sidekick"""

    data = get_pubsub_data(data)
    project_id = data["project_id"]

    logger.info("[SIDEKICK PREPROCESS] project_id: %s", project_id)

    try:
        texts, doc_ids, language = load_documents(project_id)
        tfidf, features, doc_svd = process_text(project_id, texts)
        doc_embedding_(project_id, language, tfidf, features, doc_svd, doc_ids)
    except Exception:  # pylint: disable=broad-except
        send_sidekick_update(project_id, {"status": "error"})
    else:
        send_sidekick_update(project_id, {"status": "success"})
