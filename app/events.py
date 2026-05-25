"""
In-memory event broker for Server-Sent Events.

Simple per-business pub/sub. Each connected SSE client gets its own asyncio.Queue.
When server-side code publishes an event for a business, every queue listening for
that business receives it.

This is intentionally in-memory: single-process only. For multi-worker deploys
you'd back this with Redis pub/sub.
"""

import asyncio
import json
from collections import defaultdict
from typing import AsyncIterator

# business_id 
_subscribers: dict[int, set[asyncio.Queue]] = defaultdict(set)


def publish(business_id: int, event_type: str, payload: dict | None = None) -> None:
    """Fire-and-forget publish. Safe to call from any async code."""
    event = {"type": event_type, "payload": payload or {}}
    for queue in list(_subscribers.get(business_id, ())):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            # Drop the event for this slow consumer rather than block.
            pass


async def subscribe(business_id: int) -> AsyncIterator[str]:
    """
    Subscribe to a business's event stream. Yields SSE-formatted strings ready
    to be written to the response.

    Cleans up the queue on disconnect (caller handles CancelledError).
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    _subscribers[business_id].add(queue)
    try:
        # Initial hello so the client knows the stream is alive
        yield _format_sse({"type": "connected", "payload": {}})

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=25.0)
                yield _format_sse(event)
            except asyncio.TimeoutError:
                # Keep-alive ping so proxies don't kill an idle connection
                yield ": ping\n\n"
    finally:
        _subscribers[business_id].discard(queue)


def _format_sse(event: dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event['payload'])}\n\n"
