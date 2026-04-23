# Agentic File Analysis — TODO

Status tracking for the agentic "analyze file" feature (backend → agent tool → frontend streaming UI).

---

## Goal
Provide an agent-friendly, scalable file analysis flow that: 
- Supports quick and deep (chunked) analysis
- Streams progress and partial summaries into the LangGraph session WebSocket
- Offers client-side confirmation for large/deep runs and a streaming UI to follow progress
- Optionally creates Change Request drafts from actionable findings

---

## Tasks

1. Backend: Add REST analyze endpoint
   - [x] POST `/api/projects/{id}/workspace/files/analyze/` (quick/deep)
   - [x] Quick summary heuristics (line/char counts, TODOs, language)
   - [x] Deep analysis: chunking + per-chunk heuristic summarization
   - [x] Stream progress and final summary to `langgraph_session_{session_id}` group via Channels
   - Notes: Implemented in `backend/api/workspace_file_views.py` as `analyze_file` action.

2. Backend: LangGraph tool for analyze-file
   - [x] Add `analyze_file` tool to workspace tools (supports `mode` and optional `session_id`) to be callable by agents
   - Notes: Implemented in `backend/api/frameworks/langgraph/tools.py`.

3. Backend: LangGraph stream consumer enhancements
   - [x] Make `LangGraphStreamConsumer` join a per-session group to receive server-initiated analyze updates
   - [x] Add handler to forward `analyze_update` group messages to connected clients
   - Notes: Implemented in `backend/api/consumers.py` (joins `langgraph_session_{session_id}`).

4. Frontend: Add client API for analyze
   - [x] `analyzeWorkspaceFile` client helper (POST to analyze endpoint)
   - Notes: Implemented in `src/lib/api.ts`.

5. Frontend: UI & UX
   - [x] Add "Deep Analyze" button in `FileExplorer` with confirmation for large files
   - [x] Pass `currentSessionId` into `FileExplorer` for streaming
   - [x] Wire agent WebSocket hook to handle `analyze_chunk` and `analyze_complete` events
   - [ ] Add a dedicated streaming modal/UI with live progress, chunk previews, and final summary (planned)
   - [ ] Add option to create a Change Request draft from the final analysis (planned)

6. Agent integration & tooling
   - [ ] Make agent tool calls include `session_id` automatically so agents can request streamed deep analyses
   - [ ] Add LLM-based chunk summarization (e.g., per-chunk LLM prompts, map-reduce style)
   - [ ] Add token/cost estimation for deep runs and require approval for high-cost requests

7. Tests & Validation
   - [ ] Unit tests for endpoint (quick/deep) including permission checks
   - [ ] Integration test for channel-layer streaming (consumer receives chunk events)
   - [ ] E2E manual test to exercise stream UI with a realistic large file

---

## Next actions
- Implement the frontend streaming modal and integrate with `analysisChunks`/`analysisFinal` state (start UI work next).
- Add LLM-based per-chunk summarization in backend and make it configurable (LLM choice, temperature, token limits).
- Add tests for backend and consumer streaming.

---

*Last updated: (automated) — Backend analyze endpoint & tool implemented.*
