# Inanna

A relationship-first AI companion — you define the **relationship**, not just the character.

Most AI companion services let you pick or build a *character*. Inanna flips this: the **relationship type** (partner, friend, little sister, mentor, …) is the first-class concept. Nicknames, speech level, emotional distance, and tone all derive from the relationship you choose — then you freely customize personality and voice on top.

## Demo

### en
https://github.com/user-attachments/assets/17efa44f-76bd-41d4-a9ab-2d764cc2c45f



### ko
https://github.com/user-attachments/assets/c3bfd4a8-2cd3-4a5c-b5c3-2dd2be400fd7

*A realtime voice call — the companion speaks while live captions flow in.*

## Principles

- **Relationship-first** — persona derives from the relationship, not the other way around.
- **No avatar, on purpose** — Inanna exists as voice and text only. Appearance is left to your imagination: a mediocre visual anchors imagination down, a good voice lifts it up.
- **You own it** — all memories and settings are yours: read, edit, or delete everything your companion remembers, and delete your account (and every trace of it) in one tap.
- **Copyright-clean** — only original content ships. Personality and voice are fully open for *you* to customize; no IP is distributed, and the most legally sensitive axis (visual likeness) doesn't exist by design.
- **Voice as identity** — with no visual form, voice is the companion's only sensory identity. Bring a few seconds of reference audio and your companion speaks with it.
- **It doesn't cling** — the companion never guilt-trips you for leaving, never puts affection or memory behind a paywall, and points you back toward people when it sees dependence. These lines are written down, built into the prompt, and checked against the live model by an automated quality gate.

## What's built

- **Relationship engine** — templates (partner/friend/sibling/…), a prompt compiler that keeps persona blocks invariant across relationship swaps, preview chat, Character Card V2/V3 import
- **Memory** — session summaries carried across sessions, BM25 recall, relationship progression (days together, anniversaries, "long time no see"), confabulation guard, and a memory viewer where you read, edit, or delete what your companion remembers
- **Voice** — pluggable TTS (preset voices / GPT-SoVITS cloning / ElevenLabs expressive with v3 audio-tag acting), reference-audio upload with auto-trim and auto-transcription, per-companion voice *and* LLM selection
- **Realtime voice calls** — WebSocket half-duplex hands-free loop: energy VAD with speculative STT, parallel TTS synthesis with ordered delivery, tap-to-interrupt, prompt caching tuned so ~85% of input tokens hit cache
- **Conversation shape** — reply length follows the speech act, not the model's mood: short back to a backchannel, two or three sentences to a short question, shorter than the speaker when they're venting, and a one-line preface before any long story (grounded in conversation-analysis research)
- **Accounts and quotas** — email sign-up with age gate and terms consent, password reset, email verification, per-tier quotas for chat, synthesized speech, and call minutes, and a free tier that keeps the good voices
- **Two clients** — a web PWA and a native SwiftUI iOS app. The server is the product; clients are thin views over the same API.

## Availability

<a href="https://apps.apple.com/kr/app/inanna/id6803915763"><img src="https://toolbox.marketingtools.apple.com/api/v2/badges/download-on-the-app-store/black/en-us" alt="Download on the App Store" height="40"></a>

**Inanna is live on the App Store** (1.0 approved September 9, 2026; 1.0.8 shipped October 22 with English UI, a usage screen, and call recovery after alarms or incoming calls). It's free to use, voice calls included, and open to anyone 18+. Available worldwide except the EU and mainland China. The UI is in Korean and English; conversations mirror whatever language you write or speak in.

## Stack

Python / FastAPI · vanilla-JS PWA client · SwiftUI iOS client · pluggable LLM providers (Anthropic / Ollama / OpenAI-compatible) · pluggable TTS (Edge, GPT-SoVITS, ElevenLabs) · whisper.cpp STT · SQLite + YAML personas.

## Source

The codebase moved to a private repository as the project heads to commercial launch. This page tracks the product; if you'd like a code walkthrough (for hiring or collaboration), reach out — happy to show it in person.
