"""
hooks.py — Pre and post tool execution hooks
CCA Domain 1: Cross-cutting concerns via hooks

Hooks handle deterministic, infrastructure-level concerns:
- Logging every tool call with timestamp
- Injecting auth tokens into API calls
- Blocking dangerous actions before execution

These are NOT in the system prompt — they're code.
Prompt-based safety is unreliable. Hooks are not.
"""

import structlog
from datetime import datetime

log = structlog.get_logger(__name__)

# Tools that should never be called in production
BLOCKED_TOOLS: set[str] = set()

# Tools that require extra logging
SENSITIVE_TOOLS: set[str] = {"write_report", "save_finding"}


def pre_tool_hook(agent_name: str, task: any) -> None:
    """
    Runs before every agent call.

    Handles:
    - Timestamp logging for every tool call
    - Blocking dangerous actions before execution
    - Auth token injection (future)
    """
    log.info(
        "agent_pre_hook",
        agent=agent_name,
        timestamp=datetime.utcnow().isoformat(),
    )

    # Block any tools on the blocklist
    if agent_name in BLOCKED_TOOLS:
        raise PermissionError(
            f"Agent {agent_name} is blocked in this environment"
        )


def post_tool_hook(agent_name: str, result: any) -> None:
    """
    Runs after every successful agent call.

    Handles:
    - Result logging
    - Metrics collection (future)
    - Audit trail for sensitive operations
    """
    if agent_name in SENSITIVE_TOOLS:
        log.info(
            "sensitive_agent_completed",
            agent=agent_name,
            timestamp=datetime.utcnow().isoformat(),
        )
    else:
        log.info(
            "agent_post_hook",
            agent=agent_name,
            timestamp=datetime.utcnow().isoformat(),
        )
