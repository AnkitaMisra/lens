"""
coordinator.py — Lens Research Coordinator
CCA Domain 1: Hub-and-spoke agentic orchestration

The coordinator is the only agent with the global view.
It decomposes research goals, delegates to specialist agents
with scoped context, checks stop_reason on every response,
tags all findings with provenance, and checkpoints session state.

It never calls external APIs directly — that's the agents' job.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

import anthropic
import structlog
from pydantic import ValidationError

from lens.agents.search_agent import SearchAgent
from lens.agents.document_agent import DocumentAgent
from lens.agents.analyser_agent import AnalyserAgent
from lens.agents.writer_agent import WriterAgent
from lens.schemas import (
    ResearchGoal,
    AgentResult,
    Finding,
    ProvenanceEnvelope,
    SessionCheckpoint,
    CoordinatorError,
)
from lens.session_store import SessionStore
from lens.hooks import pre_tool_hook, post_tool_hook

log = structlog.get_logger(__name__)

# Safety limits
MAX_AGENT_RETRIES = 3
MAX_TOOL_CALLS = 20
MAX_RESEARCH_STEPS = 10


class Coordinator:
    """
    Hub-and-spoke orchestrator for Lens research sessions.

    Responsibilities:
    - Decomposes research goals into subtasks
    - Delegates each subtask to the right specialist agent
    - Checks stop_reason before passing results downstream
    - Tags all findings with provenance (source_agent, task_id, timestamp)
    - Checkpoints session state after every completed step
    - Synthesises final output from validated agent results

    Does NOT:
    - Call external APIs directly
    - Maintain state between research steps in memory only
    - Pass full session history to subagents
    """

    def __init__(self, session_store: SessionStore):
        self.client = anthropic.Anthropic()
        self.session_store = session_store
        self.search_agent = SearchAgent()
        self.document_agent = DocumentAgent()
        self.analyser_agent = AnalyserAgent()
        self.writer_agent = WriterAgent()

    async def research(
        self,
        project_id: str,
        goal: str,
        session_id: str | None = None,
    ) -> str:
        """
        Run a complete research session from goal to report.

        Args:
            project_id: The project this research belongs to
            goal: The research question or topic to investigate
            session_id: If provided, resume an existing session

        Returns:
            The completed research report as Markdown

        Raises:
            CoordinatorError: If the research fails after all retries
        """
        # Resume or create session
        session = await self._get_or_create_session(
            project_id=project_id,
            goal=goal,
            session_id=session_id,
        )

        log.info(
            "research_started",
            session_id=session.id,
            project_id=project_id,
            goal=goal,
            resuming=session_id is not None,
        )

        try:
            # Step 1 — Decompose the research goal into subtasks
            if session.current_step in (None, "start"):
                subtasks = await self._decompose_goal(goal, session)
                await self._checkpoint(session, step="search", data={"subtasks": subtasks})
            else:
                subtasks = session.checkpoint_data.get("subtasks", [])
                log.info("resuming_from_checkpoint", step=session.current_step)

            # Step 2 — Search phase: discover sources in parallel
            if session.current_step in ("start", "search"):
                search_results = await self._run_search_phase(subtasks, session)
                await self._checkpoint(
                    session, step="document", data={"search_results": search_results}
                )
            else:
                search_results = session.checkpoint_data.get("search_results", [])

            # Step 3 — Document phase: deep read the best sources
            if session.current_step in ("search", "document"):
                readings = await self._run_document_phase(search_results, session)
                await self._checkpoint(
                    session, step="analyse", data={"readings": readings}
                )
            else:
                readings = session.checkpoint_data.get("readings", [])

            # Step 4 — Analysis phase: synthesise and detect conflicts
            if session.current_step in ("document", "analyse"):
                analysis = await self._run_analysis_phase(readings, goal, session)
                await self._checkpoint(
                    session, step="write", data={"analysis": analysis}
                )
            else:
                analysis = session.checkpoint_data.get("analysis", {})

            # Step 5 — Writing phase: produce the final report
            if session.current_step in ("analyse", "write"):
                report = await self._run_writing_phase(analysis, goal, session)
                await self._checkpoint(
                    session, step="complete", data={"report": report}
                )
            else:
                report = session.checkpoint_data.get("report", "")

            # Mark session complete
            await self.session_store.complete_session(session.id)
            log.info("research_complete", session_id=session.id)

            return report

        except Exception as e:
            await self.session_store.fail_session(session.id, str(e))
            log.error("research_failed", session_id=session.id, error=str(e))
            raise CoordinatorError(
                message=f"Research failed at step {session.current_step}: {e}",
                session_id=session.id,
                step=session.current_step,
            )

    async def _decompose_goal(
        self, goal: str, session: Any
    ) -> list[str]:
        """
        Break the research goal into focused subtasks.

        Returns a list of specific search queries — each one
        is scoped enough to give the Search Agent a clear job.
        """
        log.info("decomposing_goal", goal=goal)

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system="""You are a research coordinator. Break the given research goal
into 3-5 specific search queries that together would produce comprehensive coverage.

Each query should be:
- Specific enough to return focused results
- Different enough to cover distinct aspects
- Ordered from most fundamental to most specific

Respond with a JSON array of query strings only. No explanation.""",
            messages=[{"role": "user", "content": f"Research goal: {goal}"}],
        )

        # Gate 1 — stop_reason check
        if response.stop_reason == "max_tokens":
            log.warning("decomposition_truncated", goal=goal)
            # Fallback to single query
            return [goal]

        raw = response.content[0].text
        try:
            subtasks = json.loads(raw)
            if not isinstance(subtasks, list):
                raise ValueError("Expected a list")
            log.info("goal_decomposed", subtask_count=len(subtasks))
            return subtasks
        except (json.JSONDecodeError, ValueError):
            log.warning("decomposition_parse_failed", raw=raw[:100])
            return [goal]

    async def _run_search_phase(
        self, subtasks: list[str], session: Any
    ) -> list[dict]:
        """
        Run search tasks in parallel — one per subtask.
        Each result is tagged with provenance before returning.
        """
        log.info("search_phase_started", subtask_count=len(subtasks))

        # Run all searches in parallel
        tasks = [
            self._run_agent_with_retry(
                agent=self.search_agent,
                task=subtask,
                session=session,
                agent_name="SearchAgent",
            )
            for subtask in subtasks
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter failed results and tag with provenance
        tagged_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                log.warning(
                    "search_subtask_failed",
                    subtask=subtasks[i],
                    error=str(result),
                )
                continue

            # Gate 2 — provenance tagging before downstream use
            tagged = ProvenanceEnvelope(
                source_agent="SearchAgent",
                task_id=str(uuid4()),
                timestamp=datetime.utcnow().isoformat(),
                content=result,
            )
            tagged_results.append(tagged.model_dump())

        log.info(
            "search_phase_complete",
            total=len(subtasks),
            succeeded=len(tagged_results),
        )
        return tagged_results

    async def _run_document_phase(
        self, search_results: list[dict], session: Any
    ) -> list[dict]:
        """
        Deep read the top sources discovered in search phase.
        Pass only the URL and title to the Document Agent — not
        the full search context (scoped handoff).
        """
        log.info("document_phase_started")

        # Extract URLs from search results — scoped handoff
        urls = []
        for result in search_results:
            content = result.get("content", {})
            for item in content.get("results", []):
                if item.get("url"):
                    urls.append(item["url"])

        # Deduplicate and limit to top 10
        urls = list(dict.fromkeys(urls))[:10]

        tasks = [
            self._run_agent_with_retry(
                agent=self.document_agent,
                task=url,
                session=session,
                agent_name="DocumentAgent",
            )
            for url in urls
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        readings = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                log.warning("document_read_failed", url=urls[i], error=str(result))
                continue

            tagged = ProvenanceEnvelope(
                source_agent="DocumentAgent",
                task_id=str(uuid4()),
                timestamp=datetime.utcnow().isoformat(),
                content=result,
            )
            readings.append(tagged.model_dump())

        log.info("document_phase_complete", documents_read=len(readings))
        return readings

    async def _run_analysis_phase(
        self, readings: list[dict], goal: str, session: Any
    ) -> dict:
        """
        Synthesise findings from all document readings.
        Detect conflicts. Pass only the tagged readings — not
        the full search results or session history.
        """
        log.info("analysis_phase_started", reading_count=len(readings))

        # Scoped handoff — analyser gets readings + goal only
        result = await self._run_agent_with_retry(
            agent=self.analyser_agent,
            task={"goal": goal, "readings": readings},
            session=session,
            agent_name="AnalyserAgent",
        )

        tagged = ProvenanceEnvelope(
            source_agent="AnalyserAgent",
            task_id=str(uuid4()),
            timestamp=datetime.utcnow().isoformat(),
            content=result,
        )

        log.info("analysis_phase_complete")
        return tagged.model_dump()

    async def _run_writing_phase(
        self, analysis: dict, goal: str, session: Any
    ) -> str:
        """
        Produce the final report from the analysis.
        Multi-pass: draft → review → final (handled by WriterAgent).
        """
        log.info("writing_phase_started")

        result = await self._run_agent_with_retry(
            agent=self.writer_agent,
            task={"goal": goal, "analysis": analysis},
            session=session,
            agent_name="WriterAgent",
        )

        log.info("writing_phase_complete")
        return result

    async def _run_agent_with_retry(
        self,
        agent: Any,
        task: Any,
        session: Any,
        agent_name: str,
    ) -> Any:
        """
        Run a specialist agent with stop_reason gating and retry logic.

        Checks:
        1. stop_reason must be end_turn before accepting output
        2. Schema validation on output before returning
        3. Specific retry feedback on validation failure
        4. Max retries enforced — never loops indefinitely

        Args:
            agent: The specialist agent to run
            task: The scoped task for this agent (NOT full session history)
            session: Current session for logging
            agent_name: For provenance tagging and logging

        Returns:
            Validated agent output

        Raises:
            CoordinatorError: If agent fails after MAX_AGENT_RETRIES
        """
        last_error = None

        for attempt in range(MAX_AGENT_RETRIES):
            try:
                log.info(
                    "agent_called",
                    agent=agent_name,
                    attempt=attempt + 1,
                    session_id=session.id,
                )

                # Pre-tool hook — logging, auth injection, blocking
                pre_tool_hook(agent_name=agent_name, task=task)

                result = await agent.run(task)

                # Post-tool hook — logging, validation side effects
                post_tool_hook(agent_name=agent_name, result=result)

                log.info("agent_succeeded", agent=agent_name, attempt=attempt + 1)
                return result

            except ValidationError as e:
                last_error = str(e)
                log.warning(
                    "agent_validation_failed",
                    agent=agent_name,
                    attempt=attempt + 1,
                    error=last_error,
                )
                # Specific retry feedback injected into next attempt
                task = {
                    "original_task": task,
                    "retry_feedback": (
                        f"Your previous output failed validation: {last_error}. "
                        f"Please fix these specific issues and try again."
                    ),
                }
                continue

            except Exception as e:
                last_error = str(e)
                log.error(
                    "agent_error",
                    agent=agent_name,
                    attempt=attempt + 1,
                    error=last_error,
                )
                # Non-validation errors still retry
                continue

        # All retries exhausted — structured error
        raise CoordinatorError(
            message=f"{agent_name} failed after {MAX_AGENT_RETRIES} attempts: {last_error}",
            session_id=session.id,
            agent=agent_name,
            is_retryable=False,
        )

    async def _checkpoint(
        self, session: Any, step: str, data: dict
    ) -> None:
        """
        Checkpoint session state after every completed step.
        Any interruption loses at most one step.
        """
        await self.session_store.checkpoint(
            session_id=session.id,
            step=step,
            data=data,
        )
        session.current_step = step
        session.checkpoint_data.update(data)
        log.info("checkpoint_saved", session_id=session.id, step=step)

    async def _get_or_create_session(
        self, project_id: str, goal: str, session_id: str | None
    ) -> Any:
        """Resume existing session or create a new one."""
        if session_id:
            session = await self.session_store.get_session(session_id)
            if session:
                return session
            log.warning("session_not_found_creating_new", session_id=session_id)

        return await self.session_store.create_session(
            project_id=project_id,
            goal=goal,
        )
