# Inanna

A self-hosted, customizable AI companion — you define the **relationship**, not just the character.

Most AI companion services let you pick or build a *character*. Inanna flips this: the **relationship type** (partner, friend, little sister, mentor, …) is the first-class concept. Nicknames, speech level, emotional distance, and tone all derive from the relationship you choose — then you freely customize personality and voice on top.

## Principles

- **Relationship-first** — persona derives from the relationship, not the other way around.
- **No avatar, on purpose** — Inanna exists as voice and text only. Appearance is left to your imagination: a mediocre visual anchors imagination down, a good voice lifts it up.
- **You own it** — self-hosted, all memories and settings live in local files. The relationship doesn't die when a service shuts down.
- **Copyright-clean** — the project ships only original content. Personality and voice are fully open for *you* to customize; no IP is distributed, and the most legally sensitive axis (visual likeness) doesn't exist by design.
- **Voice as identity** — with no visual form, voice is the companion's only sensory identity. Bring a few seconds of reference audio and your companion speaks with it (pluggable local TTS engines).

## Quickstart (P0)

```bash
python3 -m venv .venv && .venv/bin/pip install -e .
export ANTHROPIC_API_KEY=sk-ant-...   # or: INANNA_PROVIDER=ollama INANNA_OLLAMA_MODEL=qwen2.5:7b
.venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8787
```

Open `http://localhost:8787` (or via Tailscale from your phone). Build a companion — pick a **relationship** first, tune the derived nickname / speech level / distance, then personality and speech quirks. Use the **preview chat** tab to test-drive the persona before saving. Conversations are summarized into memories that carry over to the next session. Character Card V2/V3 (PNG/JSON) import is supported.

Config lives in env vars or a `.env` file at the project root (real env wins). Keys: `INANNA_PROVIDER` (`anthropic`|`ollama`|`openai`), `INANNA_MODEL`, `INANNA_OLLAMA_MODEL`, `INANNA_OPENAI_BASE_URL`/`_API_KEY`/`_MODEL` (any OpenAI-compatible endpoint — OpenAI, OpenRouter, Groq, LM Studio, llama.cpp, vLLM), `INANNA_SUMMARY_PROVIDER`/`_MODEL` (separate model for memory summaries), `INANNA_DB`, `INANNA_SESSION_GAP`, `INANNA_AUTH_TOKEN` (set to require `Authorization: Bearer` on all API calls — recommended when exposing beyond localhost), `INANNA_SOVITS_URL` (GPT-SoVITS api_v2 worker for voice cloning), `INANNA_WHISPER_URL` (STT worker), `INANNA_ELEVENLABS_API_KEY` (expressive commercial TTS, optional).

Each companion can override the global LLM in the builder (모델 섹션) — memories and relationship data stay identical regardless of model. Note: small local models degrade Korean persona quality noticeably (tested: qwen2.5:7b leaks Chinese mid-sentence); treat local as the privacy/cost option, cloud as the quality option.

### Voice cloning (GPT-SoVITS)

Preset voices (Edge TTS) work out of the box. For cloning a voice from a 3–10s reference clip, run a [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) api_v2 worker and point `INANNA_SOVITS_URL` at it:

```bash
bash scripts/start-sovits.sh   # expects the repo at ~/dev/GPT-SoVITS (see the script)
INANNA_SOVITS_URL=http://127.0.0.1:9880 .venv/bin/uvicorn server.main:app ...
```

Then in the builder: voice engine → 보이스 클로닝, upload a 3–10s reference clip (and its transcript for better quality). On Apple Silicon use CPU inference (`device: cpu` — the v2ProPlus vocoder exceeds MPS channel limits); short sentences synthesize faster than realtime after warmup.

### Voice calls (P2)

Open a companion's chat and tap 📞 for a hands-free voice call (half-duplex: it listens while idle, ignores the mic while speaking, tap to interrupt). Requires HTTPS for the browser mic — use `tailscale serve --bg 8787` and open `https://<mac>.<tailnet>.ts.net`. The WebSocket protocol is documented in [docs/voice-protocol.md](docs/voice-protocol.md) and is the contract for future native clients.

### Resident services (launchd)

| Service | Port | Role |
|---|---|---|
| `com.inanna.server` | 8787 | Inanna API + web |
| `com.inanna.sovits` | 9880 | GPT-SoVITS voice cloning worker |
| `com.inanna.whisper` | 9881 | whisper.cpp STT worker |

## Roadmap to the App Store

The final form is a native iOS app. The server is the product — all logic and state live behind the API, and clients are thin views, so the current web UI is a development client that will be replaced by SwiftUI in P4. An early SwiftUI client lives in `app/` — it builds, but it's a pre-alpha skeleton, not yet usable day-to-day. Multi-user data scoping and bearer auth are implemented (`server/auth.py`, `server/billing.py`) but not yet exercised in production — the account tables are still empty; the product-mode swap points are auth (bearer → Sign in with Apple), storage (SQLite/YAML → Postgres), and push (APNs for proactive presence). See `docs/requirements.md` §1.5 for the App Store constraint checklist.

## Status

Implemented (P0–P2.7):

- **Relationship engine** — templates (partner/friend/sibling/…), prompt compiler that keeps persona blocks invariant across relationship swaps, preview chat, CCv2/v3 card import
- **Memory** — session summaries carried across sessions, BM25 recall of relevant memories, relationship progression (days together, anniversaries, "long time no see"), confabulation guard, and a **memory viewer** (🧠 in chat) where you can read, edit, or delete what your companion remembers — your data, literally
- **Voice** — pluggable TTS (Edge preset / GPT-SoVITS cloning / ElevenLabs expressive with v3 audio-tag acting), reference-audio upload with auto-trim + auto-transcription, per-companion voice *and* LLM model selection
- **Realtime voice calls** — WebSocket half-duplex hands-free loop: energy VAD with speculative STT (recognition overlaps the end-of-utterance wait), parallel TTS synthesis with ordered delivery, tap-to-interrupt, prompt caching tuned so ~85% of input tokens hit cache
- **QA harness** — `bash scripts/qa.sh [--llm]`: unit smoke + voice e2e + LLM quality gates (speech-level consistency, relationship derivation)

Docs (Korean): [requirements](docs/requirements.md) · [architecture](docs/architecture.md) · [prior-art research](docs/research.md) · [voice protocol](docs/voice-protocol.md)

## Stack

Python / FastAPI · vanilla-JS PWA client · pluggable LLM providers (Anthropic / Ollama / OpenAI-compatible) · pluggable TTS (Edge, GPT-SoVITS, ElevenLabs) · whisper.cpp STT · SQLite + YAML personas.

## License

[Apache-2.0](LICENSE)
