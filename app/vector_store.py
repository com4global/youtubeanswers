import numpy as np

# ==============================
# CONFIG
# ==============================

# MUST match embedding model output
# text-embedding-3-small -> 1536
# text-embedding-3-large -> 3072
EMBEDDING_DIM = 1536


# ==============================
# GLOBAL STATE (MVP STYLE)
# ==============================

vector_store: list[list[float]] = []
metadata_store: list[dict] = []


# ==============================
# HELPERS
# ==============================

def reset_index():
    """
    Reset vector store and metadata.
    IMPORTANT: Call this at the start of each request in MVP.
    """
    global vector_store, metadata_store
    vector_store = []
    metadata_store = []


def add_vectors(vectors: list[list[float]], metadata: list[dict]):
    """
    Add vectors and aligned metadata to in-memory store.

    vectors  -> List of embedding vectors
    metadata -> List of dicts (same length as vectors)
    """
    if not vectors or not metadata:
        return

    if len(vectors) != len(metadata):
        raise ValueError("Vectors and metadata length mismatch")

    vec_array = np.asarray(vectors, dtype="float32")

    # Safety check
    if vec_array.shape[1] != EMBEDDING_DIM:
        raise ValueError(
            f"Embedding dimension mismatch. "
            f"Expected {EMBEDDING_DIM}, got {vec_array.shape[1]}"
        )

    vector_store.extend(vec_array.tolist())
    metadata_store.extend(metadata)


def search(query_vector: list[float], k: int = 3):
    """
    Search in-memory vectors and return top-k metadata entries.
    """
    if not vector_store:
        return []

    q = np.asarray(query_vector, dtype="float32")
    if q.shape[0] != EMBEDDING_DIM:
        raise ValueError(
            f"Embedding dimension mismatch. "
            f"Expected {EMBEDDING_DIM}, got {q.shape[0]}"
        )

    vectors = np.asarray(vector_store, dtype="float32")
    diffs = vectors - q
    distances = np.sum(diffs * diffs, axis=1)
    top_k = min(k, len(vector_store))
    indices = np.argsort(distances)[:top_k]

    results = []
    for idx in indices:
        if 0 <= idx < len(metadata_store):
            results.append(metadata_store[idx])

    return results
