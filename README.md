# Inanna

A relationship-first AI companion — you define the **relationship**, not just the character.

Most AI companion services let you pick or build a *character*. Inanna flips this: the **relationship type** (partner, friend, little sister, mentor, …) is the first-class concept. Nicknames, speech level, emotional distance, and tone all derive from the relationship you choose — then you freely customize personality and voice on top.

## Demo

https://github.com/user-attachments/assets/75ce9049-d415-40b2-9746-dfe370505219

*Screen and audio were captured separately and merged in editing, so A/V sync drifts slightly in places.*

## Principles

- **Relationship-first** — persona derives from the relationship, not the other way around.
- **No avatar, on purpose** — Inanna exists as voice and text only. Appearance is left to your imagination: a mediocre visual anchors imagination down, a good voice lifts it up.
- **You own it** — all memories and settings are yours: read, edit, or delete everything your companion remembers, and delete your account (and every trace of it) in one tap.
- **Copyright-clean** — only original content ships. Personality and voice are fully open for *you* to customize; no IP is distributed, and the most legally sensitive axis (visual likeness) doesn't exist by design.
- **Voice as identity** — with no visual form, voice is the companion's only sensory identity. Bring a few seconds of reference audio and your companion speaks with it.

## What's built

- **Relationship engine** — templates (partner/friend/sibling/…), a prompt compiler that keeps persona blocks invariant across relationship swaps, preview chat, Character Card V2/V3 import
- **Memory** — session summaries carried across sessions, BM25 recall, relationship progression (days together, anniversaries, "long time no see"), confabulation guard, and a memory viewer where you read, edit, or delete what your companion remembers
- **Voice** — pluggable TTS (preset voices / GPT-SoVITS cloning / ElevenLabs expressive with v3 audio-tag acting), reference-audio upload with auto-trim and auto-transcription, per-companion voice *and* LLM selection
- **Realtime voice calls** — WebSocket half-duplex hands-free loop: energy VAD with speculative STT, parallel TTS synthesis with ordered delivery, tap-to-interrupt, prompt caching tuned so ~85% of input tokens hit cache
- **Two clients** — a web PWA and a native SwiftUI iOS app. The server is the product; clients are thin views over the same API.

## Availability

**The iOS app (v1.0) is currently in App Store review.** The service runs as an invite-based closed beta while it's polished for launch.

## Stack

Python / FastAPI · vanilla-JS PWA client · SwiftUI iOS client · pluggable LLM providers (Anthropic / Ollama / OpenAI-compatible) · pluggable TTS (Edge, GPT-SoVITS, ElevenLabs) · whisper.cpp STT · SQLite + YAML personas.

## Source

The codebase moved to a private repository as the project heads to commercial launch. This page tracks the product; if you'd like a code walkthrough (for hiring or collaboration), reach out — happy to show it in person.
