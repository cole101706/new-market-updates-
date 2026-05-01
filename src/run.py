"""Single-shot alert check, runs once and exits."""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sources import (
    fetch_market_news,
    fetch_economic_news,
    fetch_trump_posts,
    fetch_hormuz_news,
    fetch_maritime_data,
)
from notifier import send_push

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("alerts")

STATE_FILE = Path(__file__).parent.parent / "state.json"
MAX_STATE_SIZE = 8000
MAX_NOTIFICATIONS_PER_RUN = 25


def load_state():
    if not STATE_FILE.exists():
        return {"first_run": True, "seen": []}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception as e:
        log.warning("State file corrupt, starting fresh: " + str(e))
        return {"first_run": True, "seen": []}


def save_state(state):
    if len(state["seen"]) > MAX_STATE_SIZE:
        state["seen"] = state["seen"][-MAX_STATE_SIZE:]
    STATE_FILE.write_text(json.dumps(state, indent=2))


async def main():
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        log.error("NTFY_TOPIC environment variable is empty or missing.")
        return 1

    config = {
        "ntfy": {
            "topic": topic,
            "server": os.environ.get("NTFY_SERVER", "https://ntfy.sh"),
        },
        "market_max_age_hours": 1.0,
        "economic_max_age_hours": 6.0,
        "trump_max_age_hours": 1.5,
        "hormuz_max_age_hours": 4.0,
        "maritime": {"enabled": False},
    }

    state = load_state()
    seen = set(state.get("seen", []))
    is_first_run = state.get("first_run", True)

    fetchers = [
        ("market", fetch_market_news),
        ("economic", fetch_economic_news),
        ("trump", fetch_trump_posts),
        ("hormuz", fetch_hormuz_news),
        ("maritime", fetch_maritime_data),
    ]

    new_items = []
    seen_order = list(state.get("seen", []))

    for source_name, fn in fetchers:
        try:
            items = await fn(config)
        except Exception as e:
            log.error("[" + source_name + "] fetch failed: " + str(e))
            continue

        for item in items:
            if item["id"] in seen:
                continue
            new_items.append((source_name, item))
            seen.add(item["id"])
            seen_order.append(item["id"])

    log.info("Found " + str(len(new_items)) + " new items (first_run=" + str(is_first_run) + ")")

    if is_first_run:
        try:
            send_push(
                topic=topic,
                title="✅ Live alerts online",
                message="Setup complete. Tracking " + str(len(new_items)) + " current items. You'll only get alerts for NEW items from now on.",
                priority=3,
                tags=["white_check_mark"],
            )
            log.info("Sent startup confirmation.")
        except Exception as e:
            log.warning("Startup ping failed: " + str(e))
        state["first_run"] = False

    elif len(new_items) > MAX_NOTIFICATIONS_PER_RUN:
        log.warning("Suppressing " + str(len(new_items)) + " alerts in one cycle.")
        by_source = {}
        for src, _ in new_items:
            by_source[src] = by_source.get(src, 0) + 1
        breakdown = ", ".join(k + ": " + str(v) for k, v in by_source.items())
        try:
            send_push(
                topic=topic,
                title="⚠️ Alert flood suppressed",
                message=str(len(new_items)) + " items in one cycle. Breakdown: " + breakdown,
                priority=3,
            )
        except Exception as e:
            log.warning("Flood notice failed: " + str(e))

    else:
        for source_name, item in new_items:
            try:
                send_push(
                    topic=topic,
                    title=item["title"],
                    message=item["message"],
                    url=item.get("url"),
                    priority=item.get("priority", 3),
                    tags=[source_name] + item.get("tags", []),
                )
                log.info("[" + source_name + "] sent: " + item["title"])
            except Exception as e:
                log.error("[" + source_name + "] push failed: " + str(e))

    state["seen"] = seen_order
    save_state(state)
    log.info("State saved with " + str(len(seen_order)) + " tracked IDs.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
