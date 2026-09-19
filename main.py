"""Cloud Run entrypoint: one route, handed to Bolt."""
from fastapi import FastAPI, Request
from slack_bolt.adapter.fastapi import SlackRequestHandler

from adapters.cli import load_env

load_env()
from adapters.slack_app import app as slack_app  # noqa: E402  (after env is loaded)

app = FastAPI()
handler = SlackRequestHandler(slack_app)


@app.post("/slack/events")
async def slack_events(req: Request):
    return await handler.handle(req)


@app.get("/")
def health():
    return {"ok": True}
