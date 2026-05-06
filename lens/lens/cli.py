"""
cli.py — Lens CLI entry point
Usage: lens research "your topic"

Built with Click. All commands are async-compatible.
The CLI is a thin wrapper — all logic lives in the coordinator.
"""

import asyncio
import os
import sys
from pathlib import Path

import click
import structlog
from dotenv import load_dotenv

from lens.coordinator import Coordinator
from lens.session_store import SessionStore

load_dotenv()

# Configure structured logging
structlog.configure(
    processors=[
        structlog.dev.ConsoleRenderer(colors=True)
    ]
)

log = structlog.get_logger(__name__)


def get_store() -> SessionStore:
    """Get the session store, creating data/ dir if needed."""
    db_path = os.getenv("LENS_DB_PATH", "./data/lens.db")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return SessionStore(db_path=db_path)


@click.group()
@click.version_option(version="0.1.0", prog_name="lens")
def cli():
    """
    Lens — AI research workspace.

    Your work persists. Your research builds over time.
    """
    pass


@cli.command()
@click.argument("goal")
@click.option(
    "--project", "-p",
    default=None,
    help="Project ID to add this research to. Creates a new project if not provided.",
)
@click.option(
    "--resume", "-r",
    default=None,
    help="Session ID to resume an interrupted research session.",
)
@click.option(
    "--output", "-o",
    default=None,
    help="Save report to this file path (e.g. report.md). Prints to stdout if not set.",
)
def research(goal: str, project: str, resume: str, output: str):
    """
    Research a topic and produce a cited report.

    Examples:

    \b
    lens research "impact of LLMs on software engineering"
    lens research "quantum computing state of the art" --project my-project-id
    lens research "AI safety approaches" --resume session-id-here
    lens research "climate tech startups" --output report.md
    """
    asyncio.run(_research(goal, project, resume, output))


async def _research(
    goal: str,
    project_id: str | None,
    session_id: str | None,
    output_path: str | None,
):
    """Async implementation of the research command."""

    # Check API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        click.echo(
            "❌ ANTHROPIC_API_KEY not set.\n"
            "   Add it to .env or set it in your environment:\n"
            "   export ANTHROPIC_API_KEY=your_key_here",
            err=True,
        )
        sys.exit(1)

    store = get_store()

    # Create a project if none provided
    if not project_id:
        project = await store.create_project(
            name=f"Research: {goal[:50]}",
            description=goal,
        )
        project_id = project["id"]
        click.echo(f"📁 Created project: {project_id}")

    click.echo(f"🔍 Starting research: {goal}")
    if session_id:
        click.echo(f"▶️  Resuming session: {session_id}")

    coordinator = Coordinator(session_store=store)

    try:
        with click.progressbar(
            length=5,
            label="Researching",
            show_eta=False,
        ) as bar:
            # Run research
            report = await coordinator.research(
                project_id=project_id,
                goal=goal,
                session_id=session_id,
            )
            bar.update(5)

        click.echo("\n✅ Research complete!\n")

        # Output the report
        if output_path:
            Path(output_path).write_text(report)
            click.echo(f"📄 Report saved to: {output_path}")
        else:
            click.echo("─" * 60)
            click.echo(report)
            click.echo("─" * 60)

    except KeyboardInterrupt:
        click.echo(
            "\n⏸️  Research interrupted. Resume with:\n"
            f"   lens research \"{goal}\" --resume <session-id>",
            err=True,
        )
        sys.exit(0)

    except Exception as e:
        click.echo(f"\n❌ Research failed: {e}", err=True)
        click.echo(
            "   The session was checkpointed. Resume with:\n"
            f"   lens research \"{goal}\" --resume <session-id>",
            err=True,
        )
        sys.exit(1)


@cli.command()
@click.option("--project", "-p", default=None, help="Filter by project ID")
def sessions(project: str):
    """List research sessions."""
    asyncio.run(_sessions(project))


async def _sessions(project_id: str | None):
    store = get_store()

    if project_id:
        rows = await store.get_project_sessions(project_id)
    else:
        # Show all sessions
        rows = list(store.db["sessions"].rows_where(
            order_by="created_at desc",
            limit=20,
        ))

    if not rows:
        click.echo("No sessions found.")
        return

    click.echo(f"\n{'ID':<38} {'Status':<10} {'Step':<12} {'Goal'}")
    click.echo("─" * 90)
    for row in rows:
        goal = row["goal"][:40] + "..." if len(row["goal"]) > 40 else row["goal"]
        click.echo(
            f"{row['id']:<38} "
            f"{row['status']:<10} "
            f"{row['current_step']:<12} "
            f"{goal}"
        )


@cli.command()
@click.argument("project_name")
def new(project_name: str):
    """Create a new research project."""
    asyncio.run(_new(project_name))


async def _new(name: str):
    store = get_store()
    project = await store.create_project(
        name=name,
        description=f"Research project: {name}",
    )
    click.echo(f"✅ Created project: {name}")
    click.echo(f"   ID: {project['id']}")
    click.echo(f"\nStart researching:")
    click.echo(f"   lens research \"your topic\" --project {project['id']}")


def main():
    cli()


if __name__ == "__main__":
    main()
