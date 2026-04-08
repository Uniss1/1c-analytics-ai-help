"""ai-chat API client for knowledge base queries.

Uses existing ai-chat service (Uniss1/ai-chat) which provides:
- Hybrid search (vector + keyword + trigram) over Wiki.js
- LLM-generated answers via Ollama
- Source attribution

This module is a thin wrapper — ai-chat handles RAG, LLM and formatting.
No need for a separate LLM call (GPU 3) for knowledge flow.
"""

import httpx

from .config import settings


async def ask_knowledge_base(question: str, history: list[dict] | None = None) -> dict:
    """Ask ai-chat for an answer from the knowledge base.

    Args:
        question: user question in Russian
        history: optional chat history [{role: "user"/"assistant", content: "..."}]

    Returns:
        {answer: str, sources: [{title, path}], from_cache: bool}
    """
    async with httpx.AsyncClient(timeout=settings.wiki_timeout) as client:
        response = await client.post(
            f"{settings.wiki_base_url}/api/chat",
            json={
                "message": question,
                "history": history or [],
                "mode": "ai",
            },
        )
        response.raise_for_status()
        data = response.json()
        return {
            "answer": data["answer"],
            "sources": data.get("sources", []),
            "from_cache": data.get("from_cache", False),
        }
