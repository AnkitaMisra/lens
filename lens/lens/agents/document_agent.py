"""
document_agent.py — Lens Document Agent
Responsibility: Deep reading — extract structured claims from sources

Receives a URL from the coordinator.
Fetches full content and extracts structured claims with confidence levels.
Returns validated DocumentAgentOutput.

Does NOT search for new sources.
Does NOT analyse or compare across documents.
One document in — structured claims out.
"""

import json

import anthropic
import structlog
from pydantic import ValidationError

from lens.schemas import DocumentAgentOutput, ExtractedClaim

log = structlog.get_logger(__name__)

SYSTEM_PROMPT = """You are a document analysis specialist. Your job is to read
a document deeply and extract structured, citable claims.

You will be given a URL. Fetch and read its full content, then return
this exact JSON structure:

{
  "url": "the URL you read",
  "title": "document title",
  "summary": "2-3 sentence overview of the document",
  "claims": [
    {
      "claim": "a specific factual claim from the document",
      "quote": "direct quote supporting this claim, or null",
      "section": "which section this came from, or null",
      "confidence": "high|medium|low"
    }
  ],
  "word_count": number or null,
  "published_date": "ISO date or null",
  "author": "author name or null"
}

Rules:
- Extract 5-15 specific claims — not summaries
- Only include claims you can directly cite from the document
- Mark confidence as "low" for anything ambiguous or hedged
- Return ONLY the JSON. No preamble."""


class DocumentAgent:
    """
    Deep reading agent.

    Scoped tools: web fetch only (via built-in URL reading).
    Cannot search or save.
    Returns validated DocumentAgentOutput.
    """

    def __init__(self):
        self.client = anthropic.Anthropic()

    async def run(self, task: str | dict) -> dict:
        """
        Read a document deeply and extract structured claims.

        Args:
            task: Either a URL string or a dict with retry feedback

        Returns:
            Validated DocumentAgentOutput as dict

        Raises:
            ValidationError: If output doesn't match schema
        """
        if isinstance(task, dict) and "retry_feedback" in task:
            url = task["original_task"]
            feedback = task["retry_feedback"]
            user_message = f"URL: {url}\n\nFeedback from previous attempt: {feedback}"
        else:
            url = task
            user_message = f"URL: {url}"

        log.info("document_agent_running", url=url)

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        text_content = ""
        for block in response.content:
            if hasattr(block, "text"):
                text_content = block.text
                break

        try:
            raw = json.loads(text_content)
            output = DocumentAgentOutput(**raw)
            log.info(
                "document_agent_complete",
                url=url,
                claim_count=len(output.claims),
            )
            return output.model_dump()
        except (json.JSONDecodeError, ValidationError) as e:
            log.warning("document_agent_parse_failed", url=url, error=str(e))
            # Return minimal valid structure
            return DocumentAgentOutput(
                url=url,
                title="Unable to parse",
                summary="Document could not be fully parsed.",
                claims=[],
            ).model_dump()
