"""Implements metric lego learning"""
# Adapted from https://bitbucket.org/muckdoc/muckdoc/
# Look into faster version, e.g. from
# https://github.com/fcaldas/MetricLearning/blob/master/lego_functions.py

# Third Party
import numba
import numpy as np
from scipy import stats

# Use mathy names in this file
# pylint: disable=invalid-name


def lego_learn(doc_vectors, constraints, positive_docs):
    updated_doc_vectors, mean_vec = get_mean_vec(
        doc_vectors, constraints, positive_docs
    )
    doc_dists = fast_cosine_matrix(mean_vec, updated_doc_vectors)
    doc_percentiles = stats.rankdata(doc_dists, "average") / len(doc_dists)
    return doc_dists, doc_percentiles


@numba.njit
def update(X_i, X_j, y, A, u=7, l=10, gamma=0.08):
    # pylint: disable=too-many-arguments
    diff = X_i - X_j
    d = np.dot(diff, np.dot(A, diff))
    if (d > u and y == 1) or (d < l and y == -1):
        target = u * (y == 1) + l * (y == -1)
        _y = (
            (gamma * d * target - 1)
            + np.sqrt((gamma * d * target - 1) ** 2 + 4 * gamma * d * d)
        ) / (2 * gamma * d)
        return A - (
            (gamma * (_y - target)) / (1 + gamma * (_y - target) * d)
        ) * np.outer(np.dot(A, diff), np.dot(A, diff))
    else:
        return A


@numba.njit(parallel=True)
def fast_cosine_matrix(u, M):
    # From https://stackoverflow.com/a/47316253
    scores = np.zeros(M.shape[0])
    for i in numba.prange(M.shape[0]):  # pylint: disable=not-an-iterable
        v = M[i]
        m = u.shape[0]
        udotv = 0
        u_norm = 0
        v_norm = 0
        for j in range(m):
            if (np.isnan(u[j])) or (np.isnan(v[j])):
                continue

            udotv += u[j] * v[j]
            u_norm += u[j] * u[j]
            v_norm += v[j] * v[j]

        u_norm = np.sqrt(u_norm)
        v_norm = np.sqrt(v_norm)

        if (u_norm == 0) or (v_norm == 0):
            ratio = 1.0
        else:
            ratio = udotv / (u_norm * v_norm)
        scores[i] = ratio
    return scores


@numba.njit
def get_mean_vec_(A_updated, doc_vectors, positive_doc_vectors):
    L = np.linalg.cholesky(A_updated)
    # mean with axis is not supported in numba, so accomplish with sum
    mean_vec = np.sum(np.dot(positive_doc_vectors, L), 0) / L.shape[0]

    # Mean vector ordered list
    updated_doc_vectors = np.dot(doc_vectors, L)
    return updated_doc_vectors, mean_vec


def get_mean_vec(doc_vectors, constraints, positive_docs):

    if len(constraints) == 0:
        # No constraints, go purely off positive docs
        positive_doc_vectors = doc_vectors[positive_docs]
        mean_vec = np.mean(positive_doc_vectors, axis=0)
        return doc_vectors, mean_vec
    else:
        A_updated = batch_update(doc_vectors, constraints)
        return get_mean_vec_(A_updated, doc_vectors, doc_vectors[positive_docs])


def lego(u, v, y, r=0.5, A_prev=None):

    m = len(u)  # number of features
    # make into colume vectors [m,1]
    u = u[:, np.newaxis]
    v = v[:, np.newaxis]
    if A_prev is None:
        A_prev = np.identity(m)

    # find the current distance (mahalanobis) between u and v
    z = u - v
    y_current = float(np.dot(z.T, np.dot(A_prev, z)))  # y_hat in paper

    # find y_bar, which is an approximation of distance using the new metric
    y_bar_up = (
        r * y * y_current
        - 1
        + np.sqrt((r * y * y_current - 1) ** 2 + 4 * r * y_current ** 2)
    )
    y_bar_down = 2 * r * y_current
    y_bar = y_bar_up / y_bar_down
    y_bar = float(np.nan_to_num(y_bar))

    # calculate the new metric matrix A_new using y_bar
    A_new_up = r * (y_bar - y) * np.dot(A_prev, np.dot(np.dot(z, z.T), A_prev))
    A_new_down = 1 + r * (y_bar - y) * y_current
    A_new = A_prev - A_new_up / A_new_down

    return A_new


# iterates through the constraints and updates the A matrix
def batch_update(doc_vectors, constraints):
    A_ = np.identity(doc_vectors.shape[1])

    for doc_u, doc_v, same_class in constraints:
        u_t = doc_vectors[doc_u]
        v_t = doc_vectors[doc_v]
        if same_class == 1:
            y_t = 1
        else:
            y_t = -1
        A_ = update(u_t, v_t, y_t, A_)

    return A_
