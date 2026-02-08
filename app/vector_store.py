import faiss
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

index = faiss.IndexFlatL2(EMBEDDING_DIM)
metadata_store: list[dict] = []


# ==============================
# HELPERS
# ==============================

def reset_index():
    """
    Reset FAISS index and metadata.
    IMPORTANT: Call this at the start of each request in MVP.
    """
    global index, metadata_store
    index.reset()
    metadata_store = []


def add_vectors(vectors: list[list[float]], metadata: list[dict]):
    """
    Add vectors and aligned metadata to FAISS.

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

    index.add(vec_array)
    metadata_store.extend(metadata)


def search(query_vector: list[float], k: int = 3):
    """
    Search FAISS index and return top-k metadata entries.
    """
    if index.ntotal == 0:
        return []

    q = np.asarray([query_vector], dtype="float32")

    distances, indices = index.search(q, min(k, index.ntotal))

    results = []
    for idx in indices[0]:
        if 0 <= idx < len(metadata_store):
            results.append(metadata_store[idx])

    return results
