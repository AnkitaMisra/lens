"""
analyser_agent.py — Lens Analyser Agent
Responsibility: Synthesis + conflict detection

Receives provenance-tagged readings from the coordinator.
Cross-references claims across sources.
Flags contradictions explicitly — never silently blends conflicting data.
Returns validated AnalyserAgentOutput.

Does NOT search or fetch new documents.
Does NOT write the final report.
"""

import json

import anthropic
import structlog
from pydantic import ValidationError

from lens.schemas import AnalyserAgentOutput

log = structlog.get_logger(__name__)

SYSTEM_PROMPT = """You are a research analyst. Your job is to synthesise findings
from multiple sources and identify conflicts, patterns, and gaps.

You will receive a research goal and a list of document readings — each tagged
with their source agent and provenance. Analyse them and return this exact JSON:

{
  "goal": "the research goal",
  "key_findings": [
    "finding 1 — specific, citable, with source reference",
    "finding 2",
    ...
  ],
  "conflicts": [
    {
      "claim_a": "first conflicting claim",
      "source_a": "URL or document title",
      "claim_b": "second conflicting claim",
      "source_b": "URL or document title",
      "conflict_description": "why these conflict",
      "severity": "high|medium|low"
    }
  ],
  "confidence": "high|medium|low",
  "gaps": [
    "area where research is insufficient",
    ...
  ],
  "sources_analysed": number
}

Rules:
- NEVER silently blend conflicting claims — always flag them in conflicts[]
- Key findings must reference their source
- Empty conflicts[] means no conflicts found — that is valid
- Be specific — avoid vague generalisations
- Return ONLY the JSON. No preamble."""


class AnalyserAgent:
    """
    Synthesis and conflict detection agent.

    Receives scoped input: goal + provenance-tagged readings only.
    Never receives full session history.
    Returns validated AnalyserAgentOutput.
    """

    def __init__(self):
        self.client = anthropic.Anthropic()

    async def run(self, task: dict) -> dict:
        """
        Synthesise findings and detect conflicts.

        Args:
            task: Dict with 'goal' and 'readings' keys,
                  or retry dict with 'retry_feedback'

        Returns:
            Validated AnalyserAgentOutput as dict
        """
        if "retry_feedback" in task:
            original = task["original_task"]
            goal = original["goal"]
            readings = original["readings"]
            feedback = task["retry_feedback"]
        else:
            goal = task["goal"]
            readings = task["readings"]
            feedback = None

        log.info(
            "analyser_agent_running",
            goal=goal,
            reading_count=len(readings),
        )

        user_content = f"Research goal: {goal}\n\nReadings:\n{json.dumps(readings, indent=2)}"
        if feedback:
            user_content += f"\n\nFeedback from previous attempt: {feedback}"

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )

        text_content = ""
        for block in response.content:
            if hasattr(block, "text"):
                text_content = block.text
                break

        try:
            raw = json.loads(text_content)
            output = AnalyserAgentOutput(**raw)
            log.info(
                "analyser_agent_complete",
                findings=len(output.key_findings),
                conflicts=len(output.conflicts),
                confidence=output.confidence,
            )
            return output.model_dump()
        except (json.JSONDecodeError, ValidationError) as e:
            log.warning("analyser_agent_parse_failed", error=str(e))
            raise ValidationError(
                f"Analyser output failed validation: {e}"
            )
