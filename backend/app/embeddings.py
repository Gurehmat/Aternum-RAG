import os
from functools import lru_cache

from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "intfloat/e5-base-v2")
EMBEDDING_VECTOR_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "768"))


@lru_cache
def load_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def embed_passages(passages: list[str]) -> list[list[float]]:
    model_inputs = [f"passage: {passage}" for passage in passages]
    embeddings = load_embedding_model().encode(model_inputs, normalize_embeddings=True)
    return embeddings.tolist()


def embed_search_query(query: str) -> list[float]:
    embeddings = load_embedding_model().encode([f"query: {query}"], normalize_embeddings=True)
    return embeddings[0].tolist()
