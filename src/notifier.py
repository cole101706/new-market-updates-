"""Push notifications via ntfy.sh — free, no account required."""
import httpx


def send_push(
    topic,
    title,
    message,
    server="https://ntfy.sh",
    url=None,
    priority=3,
    tags=None,
    timeout=10,
):
    payload = {
        "topic": topic,
        "title": title,
        "message": message,
        "priority": priority,
    }
    if url:
        payload["click"] = url
    if tags:
        payload["tags"] = tags
    r = httpx.post(server, json=payload, timeout=timeout)
    r.raise_for_status()
