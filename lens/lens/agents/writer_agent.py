"""
writer_agent.py — Lens Writer Agent
Responsibility: Multi-pass report generation

Receives provenance-tagged analysis from the coordinator.
Pass 1: Draft freely
Pass 2: Review against explicit criteria (independent session)
Pass 3: Finalise incorporating review feedback

Returns validated WriterAgentOutput with full Markdown report.

Does NOT search, fetch, or analyse.
Writing and review only.
"""

import json

import anthropic
import structlog
from pydantic import ValidationError

from lens.schemas import WriterAgentOutput

log = structlog.get_logger(__name__)

DRAFT_SYSTEM = """You are a research writer. Write a comprehensive research report
based on the provided analysis and findings.

Be thorough. Cover all key findings. Note any conflicts explicitly.
Use Markdown formatting with clear headers.
Cite sources inline as [Source Title](URL).

Write the full report now."""

REVIEW_SYSTEM = """You are an independent research editor reviewing a draft report.
The reviewer who wrote this report is NOT you — review it critically.

Check the draft against these explicit criteria:
1. Every key finding has a citation
2. Conflicting findings are explicitly noted — not blended
3. Executive summary is 2-3 sentences covering the main conclusion
4. Each section has a clear header
5. No unsupported claims

For each violation, output:
[VIOLATION] section_name: description of the problem

If no violations found, output: [PASS]

Review the draft now."""

FINALISE_SYSTEM = """You are a research writer finalising a report based on editorial feedback.

Apply all [VIOLATION] feedback from the review.
If the review says [PASS], make only minor polish improvements.

Return this exact JSON:
{
  "title": "report title",
  "content_md": "full markdown report",
  "word_count": number,
  "citation_count": number,
  "executive_summary": "2-3 sentence summary"
}

Return ONLY the JSON. No preamble."""


class WriterAgent:
    """
    Multi-pass report generation agent.

    Three passes: draft → independent review → finalise.
    The same session that drafted does NOT review — independent review
    reduces bias toward the agent's own output.
    """

    def __init__(self):
        self.client = anthropic.Anthropic()

    async def run(self, task: dict) -> dict:
        """
        Generate a research report in three passes.

        Args:
            task: Dict with 'goal' and 'analysis' keys

        Returns:
            Validated WriterAgentOutput as dict
        """
        if "retry_feedback" in task:
            original = task["original_task"]
            goal = original["goal"]
            analysis = original["analysis"]
        else:
            goal = task["goal"]
            analysis = task["analysis"]

        log.info("writer_agent_started", goal=goal)

        # Pass 1 — Draft
        draft = await self._draft(goal, analysis)
        log.info("writer_draft_complete", word_count=len(draft.split()))

        # Pass 2 — Independent review
        # New API call = no memory of drafting session = unbiased review
        review = await self._review(draft)
        log.info("writer_review_complete", passed="[PASS]" in review)

        # Pass 3 — Finalise
        final = await self._finalise(draft, review, goal)
        log.info(
            "writer_agent_complete",
            word_count=final.get("word_count", 0),
            citations=final.get("citation_count", 0),
        )
        return final

    async def _draft(self, goal: str, analysis: dict) -> str:
        """Pass 1 — write the draft freely."""
        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            system=DRAFT_SYSTEM,
            messages=[{
                "role": "user",
                "content": (
                    f"Research goal: {goal}\n\n"
                    f"Analysis:\n{json.dumps(analysis, indent=2)}"
                ),
            }],
        )
        return response.content[0].text

    async def _review(self, draft: str) -> str:
        """
        Pass 2 — independent review.
        Fresh API call = no drafting context = unbiased review.
        """
        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=REVIEW_SYSTEM,
            messages=[{"role": "user", "content": f"Draft:\n{draft}"}],
        )
        return response.content[0].text

    async def _finalise(self, draft: str, review: str, goal: str) -> dict:
        """Pass 3 — apply review and produce final JSON output."""
        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=5000,
            system=FINALISE_SYSTEM,
            messages=[{
                "role": "user",
                "content": (
                    f"Goal: {goal}\n\n"
                    f"Draft:\n{draft}\n\n"
                    f"Review:\n{review}\n\n"
                    "Produce the final report JSON:"
                ),
            }],
        )

        text = response.content[0].text
        try:
            raw = json.loads(text)
            output = WriterAgentOutput(**raw)
            return output.model_dump()
        except (json.JSONDecodeError, ValidationError) as e:
            log.warning("writer_finalise_parse_failed", error=str(e))
            # Fallback — wrap draft as final output
            return WriterAgentOutput(
                title=f"Research Report: {goal[:50]}",
                content_md=draft,
                word_count=len(draft.split()),
                citation_count=draft.count("](http"),
                executive_summary="Report generated from research analysis.",
            ).model_dump()
