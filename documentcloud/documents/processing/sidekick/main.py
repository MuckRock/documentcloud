# Standard Library
import io
import logging
import math
import os
import re
from collections import Counter
from urllib.parse import urljoin

# Third Party
import environ
import fasttext
import fasttext.util
import numpy as np
import requests
import sklearn.decomposition
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer

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
VOCAB_SIZE = env.int("VOCAB_SIZE", default=30_000)
TOKEN_PATTERN = re.compile(r"(?u)\b\w\w+\b")
EMBEDDING_DIR = env.str("EMBEDDING_DIR", default="embedding")

SIDEKICK_PREPROCESS_TOPIC = publisher.topic_path(
    "documentcloud",
    env.str("SIDEKICK_PREPROCESS_TOPIC", default="sidekick-preprocess-topic"),
)

LANGUAGES = {"eng": "en"}


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
    next_ = urljoin(API_CALLBACK, f"projects/{project_id}/documents/?expand=document")

    while next_:
        response = requests.get(
            next_, headers={"Authorization": f"processing-token {PROCESSING_TOKEN}"}
        )
        # XXX check response status code
        response_json = response.json()
        next_ = response_json["next"]
        for result in response_json["results"]:
            file_names.append(
                path.text_path(result["document"]["id"], result["document"]["slug"])
            )
            languages.update([result["document"]["language"]])

    language = languages.most_common()[0][0]

    # download the files in parallel
    texts = storage.async_download(file_names)

    return texts, language


def process_text(project_id, texts):
    """Calculate the vocabulary for the corpus based on the document texts"""

    logger.info("[SIDEKICK PREPROCESS] project_id: %s - calculating vocab", project_id)

    # Derive counts for all words
    count_vectorizer = CountVectorizer(strip_accents="unicode", stop_words=None)
    counts = count_vectorizer.fit_transform(texts)

    # Calculate word frequencies
    # An array of integers, corresponding to the count of the word that appears at
    # that index in the features list
    count_by_word = np.sum(counts, axis=0).getA().flatten()
    # List of strings - All words in the corpus
    features = count_vectorizer.get_feature_names()
    # An array of indicies into the features list, sorted by most frequent
    frequencies = np.flip(np.argsort(count_by_word))

    # Reduce vocabulary to most frequent words
    # A set of the VOCAB_SIZE most frequent words
    vocab = {features[idx] for idx in frequencies[:VOCAB_SIZE]}

    logger.info("[SIDEKICK PREPROCESS] project_id: %s - bigrams", project_id)

    # Create a small bigram model on most frequent words to filter down
    # vocabulary quickly
    bigram_char_vectorizer = TfidfVectorizer(ngram_range=(2, 2), analyzer="char_wb")
    # An array of floats - I am unclear exactly how this works
    char_counts = np.asarray(
        bigram_char_vectorizer.fit_transform(
            [" ".join([features[idx] for idx in frequencies[:VOCAB_SIZE]])]
        ).todense()
    )[0]

    # Spell checking
    sym_spell = get_spell_checker(features, frequencies, count_by_word)

    def get_bigram_prob(word):
        """Approximate probability of bigram chars"""
        text = f" {word} "
        prob = 0
        count = len(text) - 1
        for i in range(count):
            bigram = text[i : i + 2]
            prob += math.log(
                char_counts[bigram_char_vectorizer.vocabulary_.get(bigram, 0)]
            )
        return prob / count

    def get_terms(word):
        """Only use words in the vocab"""
        # Return the same word if it's in the vocab
        if word in vocab:
            return [count_vectorizer.vocabulary_[word]]

        # Quick pass: remove overly long or improbable words
        if len(word) > 20 or get_bigram_prob(word) < -4:
            return []

        # Use symspell's compound search to potentially split apart words
        terms = sym_spell.lookup_compound(word, 2)[0].term.split(" ")

        # Filter terms to only include those in the reduced vocab
        # This may return nothing if there is no good spelling suggestion,
        # a single word as suggested by the spell checker, or multiple words as
        # suggested by the spell checker
        return [count_vectorizer.vocabulary_[x] for x in terms if x in vocab]

    # map words in the corpus to spell corrected words in the vocab
    # the vocab are the VOCAB_SIZE most frequent words in the corpus
    mappings = [get_terms(f) for f in features]

    # Re-compute the entire corpus with a spell-correcting tokenizer
    def spell_correcting_tokenizer(string):
        # break the string into tokens
        tokens = TOKEN_PATTERN.findall(string)
        results = []
        for token in tokens:
            # get the tokens index in the vocabulary
            # it is guarenteed to be there, since the count vectorizer includes
            # all tokens from the corpus
            idx = count_vectorizer.vocabulary_[token]

            # convert the words to their spell corrected mappings
            results.extend([features[i] for i in mappings[idx]])
        return results

    logger.info(
        "[SIDEKICK PREPROCESS] project_id: %s - spell corrected tfidf", project_id
    )

    # Derive tf-idf data on spell-corrected corpus
    spell_corrected_vectorizer = TfidfVectorizer(
        strip_accents="unicode", stop_words=None, tokenizer=spell_correcting_tokenizer
    )

    spell_corrected_tfidf = spell_corrected_vectorizer.fit_transform(texts)
    spell_corrected_features = spell_corrected_vectorizer.get_feature_names()

    logger.info("[SIDEKICK PREPROCESS] project_id: %s - svd", project_id)

    # Project tf-idf data down in dimensionality
    svd_transformer = sklearn.decomposition.TruncatedSVD(
        300, algorithm="randomized", n_iter=5
    )
    doc_svd = svd_transformer.fit_transform(spell_corrected_tfidf)

    return spell_corrected_tfidf, spell_corrected_features, doc_svd


def process_text_(project_id, texts):
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


def get_spell_checker(features, frequencies, count_by_word):
    """Create a spelling dictionary"""
    from symspellpy import SymSpell  # XXX use faster symspell

    dictionary = io.StringIO()
    for i in range(min(len(features), VOCAB_SIZE)):
        idx = frequencies[i]
        word, freq = features[idx], count_by_word[idx]
        dictionary.write(f"{word} {freq}\n")
    dictionary.seek(0)
    sym_spell = SymSpell(2, 9)
    sym_spell.load_dictionary_stream(dictionary, 0, 1, " ")
    return sym_spell


def doc_embedding(project_id, language, tfidf, features, doc_svd):
    """Calculate the doc embeddings"""

    logger.info("[SIDEKICK PREPROCESS] project_id: %s - doc embeddings", project_id)

    # Load the embedding model
    # XXX error if language not present
    language = LANGUAGES.get(language, language)
    model = fasttext.load_model(os.path.join(EMBEDDING_DIR, f"cc.{language}.300.bin"))
    embedding_vectors = np.array(
        [model.get_word_vector(feature) for feature in features]
    )

    doc_embeddings = np.dot(tfidf.A, embedding_vectors)

    # Doc vectors are just doc_svd and doc_embeddings concatenated
    doc_vectors = np.hstack((doc_svd, doc_embeddings))

    # Serialize doc vectors to file
    with storage.open(
        path.sidekick_document_vectors_path(project_id), "wb"
    ) as vectors_file:
        np.savez_compressed(vectors_file, doc_vectors)


@pubsub_function(REDIS, SIDEKICK_PREPROCESS_TOPIC)
def preprocess(data, _context=None):
    """Preprocess the documents in a project for sidekick"""

    data = get_pubsub_data(data)
    project_id = data["project_id"]

    logger.info("[SIDEKICK PREPROCESS] project_id: %s", project_id)

    texts, language = load_documents(project_id)

    tfidf, features, doc_svd = process_text_(project_id, texts)

    doc_embedding(project_id, language, tfidf, features, doc_svd)

    # XXX set status?  save params?
