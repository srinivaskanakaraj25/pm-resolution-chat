from dotenv import load_dotenv
load_dotenv()

import os
import httpx
import typer

app = typer.Typer(no_args_is_help=True)

BASE_URL = os.environ.get("API_BASE_URL", "https://pm-resolution-chat-production.up.railway.app")
API_KEY = os.environ.get("API_KEY", "")

def client() -> httpx.Client:
    return httpx.Client(
        base_url=BASE_URL,
        headers={"X-API-Key": API_KEY},
        timeout=120,
    )


@app.command()
def start(
    rocketlane_key: str = typer.Option(None, "--rocketlane-key", "-r", help="Rocketlane API key"),
) -> None:
    """Start a new conversation."""
    user = input("You: ").strip()
    if not user:
        return

    body = {"message": user}
    if rocketlane_key:
        body["rocketlane_api_key"] = rocketlane_key

    with client() as http:
        r = http.post("/conversations", json=body)
        r.raise_for_status()
        data = r.json()
        session_id = data["session_id"]
        typer.secho(f"Claude: {data['response']}", fg=typer.colors.GREEN)

    typer.secho(f"\n[session: {session_id}]", fg=typer.colors.BRIGHT_BLACK)
    typer.secho("Type /quit to exit, /normal to exit resolution mode.", fg=typer.colors.CYAN)

    with client() as http:
        while True:
            user = input("You: ").strip()

            if user == "/quit":
                break

            if user == "/normal":
                r = http.post(f"/conversations/{session_id}/exit-resolution")
                r.raise_for_status()
                typer.secho("Resolution mode exited.", fg=typer.colors.YELLOW)
                continue

            body = {"message": user}
            if rocketlane_key:
                body["rocketlane_api_key"] = rocketlane_key
            r = http.post(f"/conversations/{session_id}/message", json=body)
            r.raise_for_status()
            data = r.json()
            typer.secho(f"Claude: {data['response']}", fg=typer.colors.GREEN)


@app.command()
def ls() -> None:
    """List all previous conversations."""
    with client() as http:
        r = http.get("/conversations")
        r.raise_for_status()
        convs = r.json()

    if not convs:
        typer.secho("No conversations found.", fg=typer.colors.YELLOW)
        return

    typer.echo("#    Title                                                Date                 Mode")
    typer.echo("-" * 90)

    for i, conv in enumerate(convs, 1):
        title = conv["title"][:50].ljust(50)
        date = conv["updated_at"][:16]
        mode = conv["mode"]
        typer.echo(f"{i:<4} {title}  {date}  {mode}")


@app.command()
def resume(
    identifier: str,
    rocketlane_key: str = typer.Option(None, "--rocketlane-key", "-r", help="Rocketlane API key"),
) -> None:
    """Resume a previous conversation by index or session UUID."""
    with client() as http:
        # resolve index to session_id via ls
        try:
            index = int(identifier)
            r = http.get("/conversations")
            r.raise_for_status()
            convs = r.json()
            if not 1 <= index <= len(convs):
                typer.secho(f"No conversation at index {index}.", fg=typer.colors.RED)
                raise typer.Exit(1)
            session_id = convs[index - 1]["session_id"]
        except ValueError:
            session_id = identifier

    typer.secho(f"Resumed [session: {session_id}]", fg=typer.colors.CYAN)
    typer.secho("Type /quit to exit, /normal to exit resolution mode.", fg=typer.colors.CYAN)

    with client() as http:
        while True:
            user = input("You: ").strip()

            if user == "/quit":
                break

            if user == "/normal":
                r = http.post(f"/conversations/{session_id}/exit-resolution")
                r.raise_for_status()
                typer.secho("Resolution mode exited.", fg=typer.colors.YELLOW)
                continue

            body = {"message": user}
            if rocketlane_key:
                body["rocketlane_api_key"] = rocketlane_key
            r = http.post(f"/conversations/{session_id}/message", json=body)
            r.raise_for_status()
            data = r.json()
            typer.secho(f"Claude: {data['response']}", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()
