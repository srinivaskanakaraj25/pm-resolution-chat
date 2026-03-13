import asyncio
from dotenv import load_dotenv
load_dotenv()
import sys
import typer
from typing import Optional
from agent_client import AgentClient
from db import init_db, list_conversations, get_conversation

app = typer.Typer(no_args_is_help=True)


@app.command()
def start() -> None:
    """Start a new conversation."""
    try:
        db_conn = init_db()
    except Exception as e:
        typer.secho(
            f"Error: Could not open database. Make sure conversations.db exists and table is set up.\n{e}",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    async def run():
        agent = AgentClient(db_conn=db_conn)
        await agent.connect()

        typer.secho(
            "Agent started. Type /quit to exit, /normal to exit resolution mode.",
            fg=typer.colors.CYAN,
        )

        try:
            while True:
                user = input("You: ").strip()

                if user == "/quit":
                    break

                if user == "/normal":
                    agent.exit_resolution_mode()
                    typer.secho(
                        "Resolution mode will exit on next turn.", fg=typer.colors.YELLOW
                    )
                    continue

                await agent.send(user)

        finally:
            await agent.disconnect()

    asyncio.run(run())


@app.command()
def ls() -> None:
    """List all previous conversations."""
    try:
        db_conn = init_db()
    except Exception as e:
        typer.secho(
            f"Error: Could not open database. Make sure conversations.db exists.\n{e}",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    convs = list_conversations(db_conn)

    if not convs:
        typer.secho("No conversations found.", fg=typer.colors.YELLOW)
        return

    # Header
    typer.echo("#    Title                                                Date                 Mode")
    typer.echo("-" * 90)

    for i, conv in enumerate(convs, 1):
        title = conv["title"][:50].ljust(50)
        created = conv["updated_at"][:16]  # ISO format: YYYY-MM-DD HH:MM
        mode = conv["mode"]
        typer.echo(f"{i:<4} {title}  {created}  {mode}")


@app.command()
def resume(identifier: str) -> None:
    """Resume a previous conversation by index or session UUID."""
    try:
        db_conn = init_db()
    except Exception as e:
        typer.secho(
            f"Error: Could not open database. Make sure conversations.db exists.\n{e}",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    conv = get_conversation(db_conn, identifier)

    if not conv:
        typer.secho(
            f"Conversation not found: {identifier}",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    session_id = conv["session_id"]
    mode = conv["mode"]
    failure_context = conv["failure_context"]

    async def run():
        agent = AgentClient(db_conn=db_conn, resume_session_id=session_id)
        agent.restore_state(mode, failure_context)
        await agent.connect()

        typer.secho(
            f"Resumed conversation (mode: {mode}). Type /quit to exit, /normal to exit resolution mode.",
            fg=typer.colors.CYAN,
        )

        try:
            while True:
                user = input("You: ").strip()

                if user == "/quit":
                    break

                if user == "/normal":
                    agent.exit_resolution_mode()
                    typer.secho(
                        "Resolution mode will exit on next turn.",
                        fg=typer.colors.YELLOW,
                    )
                    continue

                await agent.send(user)

        finally:
            await agent.disconnect()

    asyncio.run(run())


if __name__ == "__main__":
    app()
