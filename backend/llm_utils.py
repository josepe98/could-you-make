"""Post-submit LLM enrichment: call the Anthropic API to draft a plan into
clarifying_notes and pick a level_of_effort. See CYM-050.

Per the project's "automated agents — never silent" rule, this module logs
loudly on every failure mode and never swallows errors silently. If
ANTHROPIC_API_KEY is unset, enrichment is skipped with a warning rather than
an exception, so the rest of the post-submit pipeline keeps working.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from anthropic import AsyncAnthropic, APIError

from .config import settings
from .database import SessionLocal
from .models import Ticket, LevelOfEffort

log = logging.getLogger("cym.llm")

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096

SYSTEM_PROMPT = """You are a senior engineer triaging incoming product tickets.

For each ticket you receive, produce:

1. A concise implementation plan: 4-8 bullet points covering the approach,
   the files/areas likely to change, any risks or open questions, and
   verification steps. Use plain markdown bullets (one per line, prefix with
   "- "). Keep total length under ~250 words.

2. A level-of-effort estimate using T-shirt sizes:
   - XS = trivial copy/config tweak, < 30 min
   - S  = small, well-scoped change, 1-2 hours
   - M  = touches multiple files or needs a small migration, half a day
   - L  = multi-day work or a meaningful new feature
   - XL = multi-week, architectural changes, or significant unknowns

Be specific and concrete. Don't lecture about general software engineering
practice. If the ticket is underspecified, call out the specific gaps in the
plan rather than padding."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "plan": {
            "type": "string",
            "description": "Implementation plan as markdown bullets, one per line.",
        },
        "level_of_effort": {
            "type": "string",
            "enum": ["XS", "S", "M", "L", "XL"],
            "description": "T-shirt-sized effort estimate.",
        },
    },
    "required": ["plan", "level_of_effort"],
    "additionalProperties": False,
}


def _build_user_message(ticket: Ticket, app_label: str) -> str:
    return (
        f"App: {app_label}\n"
        f"Type: {ticket.type}\n"
        f"Title: {ticket.title}\n"
        f"Submitter urgency: {ticket.submitter_urgency}\n"
        f"\n"
        f"Description:\n{ticket.description}"
    )


async def run_ticket_enrichment(ticket_id: int) -> None:
    """Background task: load the ticket, call Anthropic, write the plan to
    clarifying_notes and the effort estimate to level_of_effort. Fails loud
    if anything goes wrong — never silently drops."""
    if not settings.ANTHROPIC_API_KEY:
        log.warning("ANTHROPIC_API_KEY not set — skipping enrichment for ticket %d", ticket_id)
        return

    db = SessionLocal()
    try:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if ticket is None:
            log.error("Enrichment requested for non-existent ticket %d", ticket_id)
            return

        app_label = ticket.app_obj.label if ticket.app_obj else ticket.app
        display_id = ticket.display_id
        user_message = _build_user_message(ticket, app_label)

        client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        log.info("Running LLM enrichment for %s", display_id)
        try:
            response = await client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                thinking={"type": "adaptive"},
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    },
                ],
                output_config={
                    "format": {
                        "type": "json_schema",
                        "schema": OUTPUT_SCHEMA,
                    },
                },
                messages=[{"role": "user", "content": user_message}],
            )
        except APIError as e:
            log.error("Anthropic API error for %s: %s", display_id, e)
            raise

        text_block = next(
            (b.text for b in response.content if getattr(b, "type", None) == "text"),
            None,
        )
        if text_block is None:
            log.error(
                "No text block in Anthropic response for %s (stop_reason=%s)",
                display_id, response.stop_reason,
            )
            return

        try:
            parsed = json.loads(text_block)
        except json.JSONDecodeError as e:
            log.error("Could not parse LLM JSON for %s: %s | raw=%r", display_id, e, text_block)
            return

        plan = parsed.get("plan", "").strip()
        effort = parsed.get("level_of_effort")
        if not plan or effort not in {e.value for e in LevelOfEffort}:
            log.error(
                "LLM output missing plan or invalid effort for %s: %r",
                display_id, parsed,
            )
            return

        # Re-fetch in case admin already edited the row during the API call.
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if ticket is None:
            return

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        ai_note = f"[{timestamp}] [AI draft]\n\n{plan}"
        if ticket.clarifying_notes:
            ticket.clarifying_notes = f"{ai_note}\n\n---\n\n{ticket.clarifying_notes}"
        else:
            ticket.clarifying_notes = ai_note

        # Only set effort if admin hasn't already picked one.
        if ticket.level_of_effort is None:
            ticket.level_of_effort = effort

        db.commit()
        log.info(
            "Enrichment complete for %s (effort=%s, cache_read=%d, input=%d, output=%d)",
            display_id, effort,
            getattr(response.usage, "cache_read_input_tokens", 0) or 0,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
    except Exception:
        log.exception("Unhandled error during enrichment for ticket %d", ticket_id)
    finally:
        db.close()


async def _run_enrichment_safe(ticket_id: int) -> None:
    """Wrapper for BackgroundTasks — never lets an exception escape and
    crash the worker. The inner function logs loudly on every failure."""
    try:
        await run_ticket_enrichment(ticket_id)
    except Exception:
        log.exception("Background enrichment crashed for ticket %d", ticket_id)
