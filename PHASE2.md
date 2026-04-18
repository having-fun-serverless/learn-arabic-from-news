# Al-Jarida — Phase 2 Considerations

Items intentionally excluded from Phase 1. Pull from this list when planning the next iteration.

## Spaced repetition (SRS) for saved words

Use FSRS (e.g. `ts-fsrs`) entirely in the browser. Surface a review queue inside the Saved screen.

Schema: extend Dexie `savedWords` with `due`, `stability`, `difficulty`, `reps`, `lapses`.

## More sources

Add Al Jazeera Arabic, Sky News Arabia, Deutsche Welle Arabic. Each is one extra entry in the orchestrator's RSS list. Baked JSON schema needs no changes.

## Better diacritizer

If CAMeL Tools' built-in diacritizer produces noticeable errors at scale, package **Libtashkeel** into the `ProcessFunction` container. No schema change.

## Better TTS

If Web Speech API quality is uneven across devices, pre-render per-token Polly mp3s during the bake step and ship `audioUrl` per token in the baked JSON. CloudFront-cached, same caching story as the JSON.

## Abstractive summary for longer articles

If we move off RSS to a paid news API, add an AraBART-via-Bedrock summary step before the NLP step. Schema: add `summary: { raw, diacritized }`.

## PWA polish

"Add to home screen" UX, prefetch tomorrow's article when today's is opened, last-N-days available offline.

## Sound + pronunciation drill

Tap-to-record-and-compare against the Polly mp3. Only meaningful after Polly mp3s land.

## Optional cloud sync

Some users will want their saved-words list across devices. Design opt-in only: end-to-end encrypted blob in S3, key derived from a passphrase the user enters; backend never sees plaintext. Stays compatible with the no-account, no-logging stance.

## Accessibility audit

Screen-reader pass on Hebrew + Arabic mixed content; reduce-motion support; high-contrast variant.

## Telemetry — only if a real question demands it

Opt-in, anonymous, locally-aggregated; e.g. "which words do most beginners save first?" If the question can be answered without telemetry, don't add it.
