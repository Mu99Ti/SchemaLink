"""Embedding models provider with FastEmbed and fallbacks."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generates dense vector embeddings using FastEmbed or deterministic fallback."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        self.model_name = model_name
        self._fastembed_model = None
        self._init_model()

    def _init_model(self) -> None:
        try:
            from fastembed import TextEmbedding

            self._fastembed_model = TextEmbedding(model_name=self.model_name)
            logger.info("Initialized FastEmbed with model: %s", self.model_name)
        except Exception as e:
            logger.warning("FastEmbed not loaded (%s). Using fallback hash embeddings.", e)
            self._fastembed_model = None

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if self._fastembed_model is not None:
            try:
                embeddings = list(self._fastembed_model.embed(texts))
                return [e.tolist() for e in embeddings]
            except Exception as e:
                logger.error("FastEmbed error: %s. Falling back to deterministic embeddings.", e)

        # Deterministic lightweight fallback embedding (vector dim 384)
        return [self._hash_vector(t, dim=384) for t in texts]

    def embed_query(self, query: str) -> list[float]:
        results = self.embed_texts([query])
        return results[0] if results else [0.0] * 384

    def _hash_vector(self, text: str, dim: int = 384) -> list[float]:
        import hashlib
        import math

        vec = [0.0] * dim
        tokens = text.lower().split()
        if not tokens:
            return vec

        for token in tokens:
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            idx = h % dim
            val = ((h >> 8) % 100) / 50.0 - 1.0
            vec[idx] += val

        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec
