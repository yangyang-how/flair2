# 5. SSE and Redis Streams

> When the user needs to watch work happen in real time, you need a streaming channel. Choosing the right one is a design decision with permanent consequences.

## The problem

A pipeline run takes 10-15 seconds. During that time, six stages complete in sequence, with stages S1, S4, and S6 producing progress events for each individual item (each video analyzed, each persona voting, each script personalized). The user should see these events in real time — not as a final dump, not via polling, but as a live stream.

This means the backend needs to push data to the frontend, continuously, for the duration of a run.

## Three options you should know about

### Option 1: Polling

The frontend calls `GET /api/status/{id}` every N seconds.

```
Browser: "Are we done yet?"
Server:  "No."
Browser: (waits 2 seconds)
Browser: "Are we done yet?"
Server:  "No."
Browser: (waits 2 seconds)
Browser: "Are we done yet?"
Server:  "Yes, here's the result."
```

**Pros:** Simple. Works through any proxy. No persistent connections.
**Cons:** Wastes bandwidth (most responses are "no change"). Adds up to N seconds of latency between an event occurring and the frontend learning about it. At 2-second intervals, a 15-second run might poll 7-8 times, wasting 6-7 of those calls. Doesn't scale well — 1,000 concurrent users × 0.5 requests/second = 500 extra requests/second on the server.

### Option 2: WebSockets

A persistent bidirectional TCP connection between browser and server.

**Pros:** Bidirectional. Low latency. Efficient for high-frequency messages.
**Cons:** More complex (new protocol, different from HTTP). Harder to load-balance (sticky sessions or connection-aware routing). Doesn't work through some corporate proxies. No automatic reconnection — you have to build it. Bidirectionality is wasted if the client never sends messages.

### Option 3: Server-Sent Events (SSE)

A persistent unidirectional HTTP connection. The server sends events; the client listens.

**Pros:** Standard HTTP — works through proxies, CDNs, load balancers. Built-in reconnection with `Last-Event-ID`. Native browser API (`EventSource`). Simple to implement on the server side.
**Cons:** Unidirectional only (server to client). Limited to ~6 concurrent connections per domain in some browsers (HTTP/1.1 only — HTTP/2 removes this limit). Text-based (no binary).

### Flair2's choice: SSE

The decision framework is simple: **does the client need to send messages to the server mid-stream?** In Flair2, no — the browser submits a pipeline request once, then only listens. SSE is the right tool when the data flows in one direction.

**Rule of thumb:** don't pay for a WebSocket unless you need the back-channel. SSE gives you streaming, reconnection, and HTTP compatibility for free.

## How SSE works

### The browser side

```javascript
const evtSource = new EventSource("/api/pipeline/status/abc-123");
evtSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    updateUI(data);
};
```

That's it. The browser opens a long-lived HTTP connection. The server holds it open and sends events. The browser fires `onmessage` for each event. If the connection drops, the browser automatically reconnects (after a few seconds) and sends the `Last-Event-ID` header to tell the server where it left off.

### The server side

Each event is a chunk of text in a specific format:

```
id: 1618349000000-0
event: vote_cast
data: {"persona_id": "persona_42", "completed": 42, "total": 100}

```

The blank line after `data:` terminates the event. The `id:` field is what the browser sends back as `Last-Event-ID` on reconnect.

### The Flair2 implementation

**File:** `backend/app/sse/manager.py`

```python
async def sse_event_generator(
    redis: aioredis.Redis,
    run_id: str,
    cursor: str,
    request: Request,
) -> AsyncGenerator[ServerSentEvent | dict, None]:
    stream_key = STREAM_KEY.format(run_id=run_id)
    last_id = cursor

    while True:
        if await request.is_disconnected():
            break

        entries = await redis.xread(
            {stream_key: last_id},
            block=XREAD_BLOCK_MS,    # 5000ms
            count=XREAD_COUNT,       # 10 events max
        )

        if not entries:
            continue

        for stream_name, messages in entries:
            for msg_id, fields in messages:
                last_id = msg_id
                yield {
                    "id": msg_id,
                    "event": fields.get("event", "message"),
                    "data": fields.get("data", "{}"),
                }

                # Check for terminal state
                event_type = fields.get("event")
                if event_type in {"pipeline_completed", "pipeline_error"}:
                    return
```

Let's break down the critical pieces:

**The loop:** the generator runs indefinitely, yielding events as they appear. It only stops when: (a) the client disconnects, (b) a terminal event arrives (`pipeline_completed` or `pipeline_error`), or (c) an error occurs.

**`XREAD` with blocking:** `redis.xread({stream_key: last_id}, block=5000)` says "give me all entries in this stream after `last_id`, and if there are none, wait up to 5 seconds before returning empty." This is not polling — it's a blocking read. Redis holds the connection open and pushes data as soon as it arrives. The 5-second timeout exists only so the loop can check `request.is_disconnected()` periodically.

**The cursor (`last_id`):** starts at `"0-0"` (beginning of stream) for new connections, or at the `Last-Event-ID` value for reconnects. Each processed message advances the cursor. This means: if the connection drops after processing 50 events, the reconnect starts at event 51, not event 1.

## Why Redis Streams, not pub/sub

This is a design decision worth understanding deeply, because it illustrates a general principle.

### Redis pub/sub

Publisher calls `PUBLISH channel message`. All current subscribers receive it. If no one is subscribed, the message is lost. If a subscriber disconnects and reconnects, it misses everything published during the gap.

### Redis Streams

Publisher calls `XADD stream fields`. The entry is appended to a persistent, ordered log. Consumers call `XREAD` with a cursor to read entries after a given position. Entries persist until explicitly trimmed.

### Why Streams win here

**Problem 1: Late joiners.** A user opens a browser tab 5 seconds into a pipeline run. With pub/sub, they'd miss the first 5 seconds of events. With Streams, they start reading from `"0-0"` and replay the entire history. The UI shows the full progression.

**Problem 2: Reconnection.** The browser loses connection for 3 seconds (network blip, laptop sleep). With pub/sub, events published during those 3 seconds are gone. With Streams + `Last-Event-ID`, the browser reconnects and reads from where it left off. Zero events lost.

**Problem 3: Multi-tab safety.** The user has two browser tabs open on the same run. With pub/sub, you'd need separate subscriptions and they'd work fine — but each subscription is a separate Redis connection, and they're not shareable. With Streams, each tab maintains its own cursor on the same stream. Independent consumers, shared data.

**The general principle:** pub/sub is for ephemeral notifications ("something happened right now"). Streams are for durable event logs ("here is the ordered history of what happened"). If your consumer might need to replay history — for reconnection, late joining, or debugging — use a log, not pub/sub.

This is the same principle behind Apache Kafka, Amazon Kinesis, and every event sourcing system. Redis Streams are a lightweight version of the same idea.

## The event types

The orchestrator publishes these events to the stream (via `XADD`):

| Event | When | Data |
|-------|------|------|
| `pipeline_started` | Run begins | `run_id`, `total_videos`, `total_personas`, `top_n` |
| `stage_started` | Each stage begins | `stage` name, `total_items` |
| `s1_progress` | Each video analyzed | `video_id`, `completed`, `total` |
| `s2_complete` | Aggregation done | `pattern_count` |
| `s3_complete` | Generation done | `script_count` |
| `vote_cast` | Each persona votes | `persona_id`, `top_5`, `completed`, `total` |
| `s5_complete` | Ranking done | `top_ids`, `top_n` |
| `s6_progress` | Each script personalized | `script_id`, `completed`, `total` |
| `pipeline_completed` | Run finished | `run_id`, `result_count` |
| `pipeline_error` | Run failed | `stage`, `error`, `recoverable` |

**Notice the pattern:** progress events for fan-out stages (S1, S4, S6) include `completed` and `total` counts. This lets the frontend show a progress bar: "Analyzing video 37 of 100" or "42 of 100 personas have voted." The frontend doesn't need to track state — each event carries enough context to render the current state.

**Design principle — self-contained events:** each event includes all the information needed to render the UI at that moment. The consumer doesn't need to remember previous events. This is important for late joiners and reconnections — if you start reading from the middle, each event still makes sense on its own.

## SSE connection lifecycle

```
Browser                     API Task                  Redis Stream
   │                            │                          │
   │ GET /api/pipeline/status   │                          │
   │ ─────────────────────────► │                          │
   │                            │ XREAD(sse:run_id, 0-0)  │
   │                            │ ────────────────────────►│
   │                            │ (blocks, waiting)        │
   │                            │                          │
   │                            │ ◄── entries arrive ──── │ (worker publishes via orchestrator)
   │ ◄── SSE event ─────────── │                          │
   │                            │ XREAD(sse:run_id, last) │
   │                            │ ────────────────────────►│
   │                            │ (blocks again)           │
   │                            │                          │
   │ ◄── SSE event ─────────── │ ◄── more entries ────── │
   │                            │                          │
   │                            │ ◄── terminal event ──── │
   │ ◄── SSE: pipeline_done ── │                          │
   │         connection closes  │                          │
```

**Important detail:** the API task holds a connection to the browser AND a connection to Redis simultaneously. It's a bridge — it doesn't generate events, it relays them. This is why the API task's CPU usage is low even during active runs; it's mostly waiting on IO from both sides.

## Edge cases the code handles

### Client disconnects mid-stream

```python
if await request.is_disconnected():
    break
```

Every XREAD timeout (every 5 seconds), the loop checks if the client is still connected. If not, it breaks out of the loop, and FastAPI closes the response. This prevents zombie connections — SSE connections that the server thinks are alive but the browser has already closed.

### Redis connection loss

```python
except aioredis.ConnectionError:
    yield ServerSentEvent(
        data=json.dumps({
            "event": "pipeline_error",
            "error": "Lost connection to state store",
        }),
    )
    return
```

If the Redis connection drops, the SSE manager sends an error event to the browser and closes the stream. The browser will automatically attempt to reconnect (SSE spec behavior), and the new connection will resume from the last event ID.

### Already-completed runs

A browser might open an SSE connection for a run that finished 10 minutes ago. Since Redis Streams persist entries (until TTL), the SSE manager replays the entire stream from `"0-0"`, including the terminal `pipeline_completed` event. The browser sees the full history, then the connection closes. No special case needed — it's just how Streams work.

## What you should take from this

1. **SSE is the right choice when data flows one way.** Don't default to WebSockets. They're more complex and the back-channel is wasted for unidirectional use cases.

2. **Redis Streams are event logs.** They persist, they support cursors, they handle replay and reconnection naturally. Pub/sub doesn't.

3. **Blocking reads aren't polling.** `XREAD ... block=5000` is *not* the server checking every 5 seconds. Redis pushes data as soon as it arrives. The 5-second timeout is only for client-disconnect checking.

4. **Self-contained events make late joins and reconnects trivial.** If each event carries all the context needed to render the current state, consumers don't need to replay from the beginning.

5. **The SSE manager is a bridge, not a source.** It doesn't generate events — the orchestrator does. The SSE manager just relays from Redis to the browser. This separation means the event publishing logic (in the orchestrator) doesn't know or care about HTTP, SSE, or browsers.

---

***Next: [The Request Lifecycle](06-the-request-lifecycle.md) — following one click from browser to final result, connecting all the pieces.***
