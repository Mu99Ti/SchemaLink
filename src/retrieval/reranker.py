"""Lightweight Cross-Encoder Reranker using FlashRank or lexical similarity fallback."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """Reranks candidate schema elements against user query."""

    def __init__(self, model_name: str = "ms-marco-TinyBERT-L-2-v2"):
        self.model_name = model_name
        self._ranker = None
        self._init_ranker()

    def _init_ranker(self) -> None:
        try:
            from flashrank import Ranker

            self._ranker = Ranker(model_name=self.model_name)
            logger.info("Initialized FlashRank with model: %s", self.model_name)
        except Exception as e:
            logger.debug("FlashRank not available (%s). Using lexical score fallback.", e)
            self._ranker = None

    def rerank(self, query: str, candidates: list[dict[str, Any]], text_key: str = "text", top_k: int = 20) -> list[dict[str, Any]]:
        if not candidates:
            return []

        if self._ranker is not None:
            try:
                from flashrank import RerankRequest

                passages = [{"id": i, "text": c.get(text_key, "")} for i, c in enumerate(candidates)]
                rerank_req = RerankRequest(query=query, passages=passages)
                results = self._ranker.rerank(rerank_req)

                ranked_candidates = []
                for r in results[:top_k]:
                    idx = r["id"]
                    item = dict(candidates[idx])
                    item["rerank_score"] = float(r.get("score", 0.0))
                    ranked_candidates.append(item)
                return ranked_candidates
            except Exception as e:
                logger.error("FlashRank execution failed: %s. Using fallback.", e)

        # Fallback ranking using token overlap & original score
        q_tokens = set(query.lower().split())
        scored = []
        for c in candidates:
            c_copy = dict(c)
            text = c_copy.get(text_key, "").lower()
            overlap = sum(1 for t in q_tokens if t in text)
            orig = c_copy.get("score", 0.5)
            c_copy["rerank_score"] = float(orig + (overlap * 0.1))
            scored.append(c_copy)

        scored.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored[:top_k]
