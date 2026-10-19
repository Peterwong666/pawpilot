# Debug: Streamlit UI ConnectError to API

**Session ID**: `streamlit-api-connect-error`
**Started**: 2026-10-02
**Status**: [CLOSED]

## Symptom
Streamlit UI at `http://localhost:8501` shows `httpx.ConnectError: [Errno 61] Connection refused`
when clicking "Ask" on the Policy Q&A tab. The traceback points to `web/app.py:_call_api()`
performing `client.post()` against the FastAPI backend.

## Hypotheses
1. FastAPI backend is not running on `localhost:8000`.
2. `PAWPILOT_API_URL` points to the wrong host/port.
3. FastAPI started but failed/crashed or port is occupied.
4. UI lacks graceful handling for API unavailability (UX bug, not functional).
5. Network isolation issue if UI is running inside Docker.

## Evidence Log

### Step 1: Browser reproduction
- Opened `http://localhost:8501` via bsk.
- Clicked "Ask".
- Observed `httpx.ConnectError: [Errno 61] Connection refused` with full traceback.

### Step 2: Instrumentation
Added debug logging to `web/app.py:_call_api()` reporting to Debug Server at `http://127.0.0.1:7777/event`.

### Step 3: Reproduce with instrumentation
Re-clicked "Ask" with instrumentation active.
Debug Server received:
```json
{"msg": "[DEBUG] API request start", "data": {"url": "http://localhost:8000/api/ask", "method": "POST"}}
{"msg": "[DEBUG] API request failed", "data": {"url": "http://localhost:8000/api/ask", "error": "ConnectError", "detail": "[Errno 61] Connection refused"}}
```

### Step 4: Root cause analysis
- Hypothesis A confirmed: FastAPI backend is not running on `localhost:8000`.
- Hypothesis B rejected: `PAWPILOT_API_URL` was correctly defaulting to `http://localhost:8000`.
- Hypothesis C rejected: No process was listening on port 8000 before the fix verification.
- Hypothesis D confirmed as secondary issue: UI had no graceful handling for API unavailability.
- Hypothesis E rejected: UI was running directly on the host, not inside a container.

## Fix
1. **UX fix (primary)**: Modified `web/app.py:_call_api()` to catch `httpx.ConnectError` and return a structured error dict with `_api_error=True` and a user-friendly message pointing to the command to start the backend.
2. Updated all three scenario tabs (Policy Q&A, Listing Generator, Review Analysis) to check `_api_error` and display `st.error(...)` instead of accessing non-existent result fields.
3. **Operational fix**: Started FastAPI backend `uv run uvicorn app.api.main:app --host 0.0.0.0 --port 8000` for verification.

## Verification
- **API down scenario**: Re-clicked "Ask" without backend. UI now shows a clean error alert: "Cannot connect to PawPilot API at http://localhost:8000/api/ask. Please make sure the FastAPI backend is running: uv run uvicorn app.api.main:app --reload". No traceback.
- **API up scenario**: Started backend and re-clicked "Ask". UI displayed the correct answer: "The maximum title length for Pet Supplies listings is 200 characters..." with source citations.
- Debug Server post-fix logs recorded both the handled connection failure and the subsequent 200 success.

## Cleanup completed
- Removed all `# #region debug-point ... # #endregion` instrumentation blocks from `web/app.py`.
- Removed `urllib.request` debug logging and `.dbg/env` reading logic.
- Kept the `httpx.ConnectError` UX handling and `_api_error` checks in all three tabs.
- Verification: `ruff check app web eval tests scripts`, `mypy app`, and `pytest tests -q` all pass.
