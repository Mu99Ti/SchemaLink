"""Modern SOTA Query Understanding: Syntax-Preserving Relational Extraction and Schema HyDE Expansion."""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class FilterCondition(BaseModel):
    concept: str = Field(description="The business concept being filtered, e.g. 'state' or 'order date'")
    operator: str = Field(default="=", description="Inferred operator: '=', '!=', '>', '<', 'BETWEEN', 'IN', 'NOT IN'")
    value: str = Field(description="The literal value mentioned in question, e.g. 'California' or '2024'")
    potential_columns: list[str] = Field(default_factory=list, description="Likely column names in a database")


class ParsedQueryIntent(BaseModel):
    raw_query: str
    intent_type: str = Field(default="analytical", description="'analytical', 'lookup', 'aggregation', 'trend', 'negation'")
    result_grain: str | None = Field(default=None, description="Granularity of the result, e.g. 'per branch', 'per customer'")
    is_negation: bool = Field(default=False, description="Whether query asks for absence/exclusion (e.g. 'without orders')")
    rank_limit: int | None = Field(default=None, description="Extracted limit or ranking requirement, e.g. top 5")
    hypothetical_tables: list[str] = Field(default_factory=list, description="Hypothetical tables a DBA would use")
    hypothetical_columns: list[str] = Field(default_factory=list, description="Hypothetical columns needed for select, group, or filter")
    filters: list[FilterCondition] = Field(default_factory=list, description="Extracted filter expressions with relational operators")
    business_terms: list[str] = Field(default_factory=list, description="Expanded domain synonyms and acronyms")
    search_expansion_text: str = Field(default="", description="Full natural query + Additive HyDE schema anchor")


SYSTEM_PROMPT = """You are an expert Database Architect and Schema Retrieval specialist.
Your task is to analyze a natural language database question and produce a structured Schema Retrieval Plan.

CRITICAL LINGUISTIC & RELATIONAL RULES:
1. Pay close attention to prepositions and qualifiers ('by', 'per', 'without', 'not', 'after', 'before', 'top').
2. 'without' or 'no' indicates negation/antijoin (e.g., customers without orders -> need customers AND orders tables).
3. 'by' or 'per' indicates the grouping grain (e.g., per branch -> branches table / branch_id).
4. Identify literal filter values (e.g., 'California') and their relational column concepts ('state').
5. Generate an additive 'search_expansion_text' that keeps the complete original query and appends hypothetical schema DDL.

Output strictly valid JSON:
{
  "intent_type": "analytical" | "lookup" | "aggregation" | "trend" | "negation",
  "result_grain": "string",
  "is_negation": false,
  "rank_limit": null,
  "hypothetical_tables": ["table1", "table2"],
  "hypothetical_columns": ["col1", "col2"],
  "filters": [
    {"concept": "state", "operator": "=", "value": "California", "potential_columns": ["state", "state_code"]}
  ],
  "business_terms": ["synonym1"],
  "search_expansion_text": "Original query. Hypothetical schema: Table table1 (id, name). Table table2 (col1, table1_id)."
}"""


class QueryParser:
    """
    Intelligent query understanding engine following modern SOTA Text-to-SQL best practices:
    - Never strips stop words from dense vector inputs (preserves attention context).
    - Extracts structural relational markers (grain, negation, temporal ranges, rank limits).
    - Uses Additive Schema HyDE to generate candidate schema structures.
    """

    def __init__(self, llm_callable: Callable[[str, str], str] | None = None):
        self.llm_callable = llm_callable

    def parse(self, query: str) -> ParsedQueryIntent:
        """Parses natural language query into a structured Schema Retrieval Plan."""
        # 1. Custom LLM callable if provided
        if self.llm_callable is not None:
            try:
                response_str = self.llm_callable(SYSTEM_PROMPT, query)
                cleaned_json = self._extract_json(response_str)
                data = json.loads(cleaned_json)
                return ParsedQueryIntent(raw_query=query, **data)
            except Exception as e:
                logger.warning("LLM query parsing failed: %s. Using relational marker parser.", e)

        # 2. OpenAI API integration if key exists
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key and self.llm_callable is None:
            try:
                parsed = self._call_openai(query, openai_key)
                if parsed:
                    return parsed
            except Exception as e:
                logger.debug("Direct OpenAI query parsing failed: %s", e)

        # 3. Modern Relational Marker & Noun-Chunk Parser (Preserves full syntax)
        return self._relational_marker_parse(query)

    def _call_openai(self, query: str, api_key: str) -> ParsedQueryIntent | None:
        try:
            import httpx

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": os.getenv("SCHEMALINK_LLM_MODEL", "gpt-4o-mini"),
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.0,
            }
            resp = httpx.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=10.0)
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                data = json.loads(content)
                return ParsedQueryIntent(raw_query=query, **data)
        except Exception as e:
            logger.debug("Direct OpenAI call error: %s", e)
        return None

    def _extract_json(self, text: str) -> str:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return match.group(0) if match else text.strip()

    def _relational_marker_parse(self, query: str) -> ParsedQueryIntent:
        """
        Extracts semantic relational roles from prepositions, negation, and qualifiers,
        while strictly preserving the complete natural query for transformer embeddings.
        """
        text_lower = query.lower()
        words = text_lower.split()

        # 1. Detect Negation / Antijoin patterns ('without', 'never', 'no', 'not', 'except')
        negation_markers = ["without", "never", "no", "not", "except", "excluding"]
        is_negation = any(m in words for m in negation_markers)

        # 2. Extract Result Grain / Grouping dimensions ('by X', 'per X', 'for each X')
        grain = None
        for i, w in enumerate(words):
            if w in ("by", "per") and i + 1 < len(words):
                candidate = words[i + 1].strip(",.?!")
                if candidate not in ("the", "a", "an", "all", "each"):
                    grain = candidate
                    break
            elif w == "each" and i > 0 and words[i - 1] == "for" and i + 1 < len(words):
                grain = words[i + 1].strip(",.?!")
                break

        # 3. Detect Rank & Limit constraints ('top 5', 'first 10', 'highest', 'most')
        rank_limit = None
        limit_match = re.search(r"\b(top|first|limit)\s+(\d+)\b", text_lower)
        if limit_match:
            rank_limit = int(limit_match.group(2))
        elif any(w in words for w in ["highest", "most", "top", "best"]):
            rank_limit = 1

        # 4. Extract Filter Conditions from Prepositions ('in California', 'after 2024')
        filters: list[FilterCondition] = []

        # 'in <Location/Entity>'
        in_match = re.search(r"\bin\s+([A-Za-z0-9_-]+)", query)
        if in_match:
            val = in_match.group(1).strip()
            if val.lower() not in ("the", "a", "an", "all", "each", "every", "which"):
                filters.append(
                    FilterCondition(
                        concept="location_or_category",
                        operator="=",
                        value=val,
                        potential_columns=["state", "city", "country", "category", "region"],
                    )
                )

        # Temporal patterns ('after X', 'before X', 'since X')
        time_match = re.search(r"\b(after|before|since|during)\s+([A-Za-z0-9_-]+)", text_lower)
        if time_match:
            prep, t_val = time_match.group(1), time_match.group(2)
            op = ">" if prep in ("after", "since") else ("<" if prep == "before" else "=")
            filters.append(
                FilterCondition(
                    concept="temporal_range",
                    operator=op,
                    value=t_val,
                    potential_columns=["date", "created_at", "order_date", "timestamp", "year"],
                )
            )

        # 5. Hypothetical Entity Extraction (Noun Chunk candidates)
        clean_tokens = [re.sub(r"[^\w]", "", w) for w in words]
        entity_candidates = set()
        for tok in clean_tokens:
            if len(tok) > 2 and tok not in ("show", "list", "find", "give", "what", "which", "where"):
                entity_candidates.add(tok)
                # Add plural/singular variants
                if tok.endswith("s") and len(tok) > 3:
                    entity_candidates.add(tok[:-1])
                else:
                    entity_candidates.add(f"{tok}s")

        hypothetical_tables = list(entity_candidates)[:8]
        hypothetical_cols = [f"{t}_id" for t in hypothetical_tables[:4]] + list(entity_candidates)[:6]

        # 6. SOTA Additive HyDE: Keep the COMPLETE original query intact, then append pseudo-schema
        # This gives transformer attention heads full syntax, while giving BM25 rich schema keywords!
        additive_hyde = (
            f"{query} | "
            f"Hypothetical Schema Target: "
            f"Tables: {', '.join(hypothetical_tables[:6])}. "
            f"Columns: {', '.join(hypothetical_cols[:8])}. "
            f"{'Grain: ' + grain + '. ' if grain else ''}"
            f"{'Antijoin/Negation required. ' if is_negation else ''}"
            f"{'Rank limit: ' + str(rank_limit) if rank_limit else ''}"
        ).strip()

        return ParsedQueryIntent(
            raw_query=query,
            intent_type="negation" if is_negation else ("analytical" if grain else "lookup"),
            result_grain=grain,
            is_negation=is_negation,
            rank_limit=rank_limit,
            hypothetical_tables=hypothetical_tables,
            hypothetical_columns=hypothetical_cols,
            filters=filters,
            business_terms=list(entity_candidates),
            search_expansion_text=additive_hyde,
        )
