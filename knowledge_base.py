"""
rag/knowledge_base.py
━━━━━━━━━━━━━━━━━━━━
Phase 2 – RAG (Retrieval-Augmented Generation) Health Advisory

How RAG works (simplified):
  1. We have a text document of WHO/EPA health guidelines.
  2. We split it into chunks and store them in a list.
  3. When a user asks a health question, we find the most relevant chunks
     using simple keyword/TF-IDF similarity (no vector DB needed for MVP).
  4. We inject those chunks into the IBM watsonx.ai prompt so the model
     answers with grounded, accurate health facts.

For a production system you would replace the simple similarity search with
a proper vector store (Chroma, Pinecone, IBM watsonx.data, etc.).
"""

from __future__ import annotations
import os
import re

from services import ibm_watsonx_service

# ── Load the guidelines document ──────────────────────────────────────────────
_GUIDELINES_PATH = os.path.join(os.path.dirname(__file__), "health_guidelines.txt")


def _load_guidelines() -> list[str]:
    """Read health_guidelines.txt and split it into paragraph-sized chunks."""
    try:
        with open(_GUIDELINES_PATH, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return []

    # Split on double newline (paragraph boundaries)
    chunks = [c.strip() for c in re.split(r"\n{2,}", text) if c.strip()]
    return chunks


# Load once at import time
_CHUNKS: list[str] = _load_guidelines()


def _simple_similarity(query: str, chunk: str) -> float:
    """
    Rough keyword overlap score — good enough for a beginner RAG demo.
    For real apps use sentence-transformers or watsonx embeddings.
    """
    q_words = set(re.findall(r"\b\w+\b", query.lower()))
    c_words = set(re.findall(r"\b\w+\b", chunk.lower()))
    if not q_words:
        return 0.0
    overlap = q_words & c_words
    return len(overlap) / len(q_words)


def retrieve(query: str, top_k: int = 3) -> list[str]:
    """
    Return the top-k most relevant guideline chunks for the given query.
    """
    if not _CHUNKS:
        return []

    scored = [(chunk, _simple_similarity(query, chunk)) for chunk in _CHUNKS]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [chunk for chunk, _ in scored[:top_k] if _ > 0]


def answer_health_question(question: str, aqi_context: dict | None = None) -> str:
    """
    Answer a health question using RAG + IBM watsonx.ai.

    Steps:
      1. Retrieve relevant guideline chunks.
      2. Build a grounded prompt.
      3. Call IBM watsonx.ai.
      4. Fall back to a simple keyword-based answer if AI is unavailable.
    """
    context_chunks = retrieve(question)
    context_text = "\n\n".join(context_chunks) if context_chunks else "No specific guidelines found."

    aqi_info = ""
    if aqi_context:
        aqi_info = (
            f"\nCurrent AQI context: {aqi_context.get('city')} AQI={aqi_context.get('aqi')} "
            f"({aqi_context.get('category_level')})."
        )

    prompt = (
        "You are a health advisor. Use ONLY the guidelines below to answer the question.\n\n"
        f"Guidelines:\n{context_text}\n"
        f"{aqi_info}\n"
        f"Question: {question}\n\n"
        "Answer (2-3 sentences, clear and simple):"
    )

    ai_answer = ibm_watsonx_service.generate_text(prompt, max_tokens=200, temperature=0.4)
    if ai_answer:
        return ai_answer

    # Fallback: return the most relevant guideline chunk as the answer
    if context_chunks:
        return context_chunks[0]
    return (
        "I don't have specific guidelines for that question. "
        "Please consult a healthcare professional for personal medical advice."
    )
