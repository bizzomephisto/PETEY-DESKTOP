# Fish Audio spoken replies

1. Save your Fish Audio API key under **Settings → Models & API keys → API keys → Fish Audio speech**. `FISH_API_KEY` is also supported; saved keys take precedence.
2. Under **Personality & voice → Voice**, choose **Fish Audio** and paste a voice model ID rather than a full voice URL.
3. Under **Models & API keys → Spoken replies**, select `s2.1-pro-free` (the default) or `s2.1-pro`. Both are S2.1; Fish documents the free route as the same model quality with fair-use limits and without production TTFA/DPA guarantees. The optional `drama-3` model supports paired word controls; S2.1 remains the default. Old `drama-3-preview` selections migrate to the documented `drama-3` API ID.
4. Choose Normal, Balanced, or Low latency. Enable **Expressive Fish speech** and **Stream Fish speech** as desired; both default on. Save and activate the Petey profile for your chat. The active chat's assigned profile controls its voice and expression behavior.
5. Enable **Automatically speak replies**, or press a reply's **Speak** button.

## Emotion and expression

When Fish is the effective speech provider and expressive speech is enabled on an S2 model, the chat model receives instructions to choose context-appropriate emotion, delivery, vocal-event, pause, and inline emphasis cues that fit its current personality and the meaning of its words. It receives Fish’s documented vocabulary plus guidance for natural-language modifiers. There is no one-tag-per-sentence restriction or tag quota. Compatible cues may be layered (generally up to three); neutral passages remain untagged. Distress calls for sympathy or calm support, factual explanations for measured delivery, and excitement only for genuinely exciting content. The instructions forbid arbitrary mood changes, contradictory cues, laughter at distress, and invented user feelings. This does not make an extra model request or replace PETEY's persona.

PETEY uses namespaced internal markers such as `[[fish:dryly sarcastic]]` to distinguish delivery instructions from ordinary bracketed text, links, and code. The Fish speech transport receives `[dryly sarcastic]`. Markers remain in the saved reply so replays retain the original expression. Other speech providers remove these internal markers; ordinary `[bracketed text]` is preserved.

**Show emotion cues in chat** displays those markers as readable directions, such as `[warm and curious]`. It defaults off, saves immediately as an installation-wide chat display preference, and updates existing replies without changing their stored text or speech. Copy follows the visible text; Speak retains the delivery cues. Visual Mode captions omit the internal directions. Expression generation and streaming settings save with each profile; display preference remains shared across profiles.

S2.1 supports sentence-level emotion and inline delivery changes. For example, a naturally justified reaction can combine `[surprised][gasping]`, and `[emphasis]` goes directly before the important word or phrase. Pauses use `[break]` or `[long-break]`. Namespaced internal equivalents keep the display toggle independent from speech.

**Paired tags are model-specific.** Fish documents `<whisper>`, `<emphasis>`, `<soft>`, `<fast>`, `<slow>`, `<stress>`, and `<forceful>` for **Drama 3**. When that model is selected, PETEY can generate balanced internal word spans such as `[[fish:<emphasis>]]HOLY SHIT![[fish:</emphasis>]]`, which become `<emphasis>HOLY SHIT!</emphasis>` for Fish. Such a reaction is an example for an actually startling situation and a compatible persona, not a canned reaction to every success. Chat displays those tags as inert text when cues are visible and shows only the words when hidden. Streaming does not split an unfinished word span, including at punctuation inside it. Other speech providers strip the internal controls. Replaying a Drama span with S2 degrades it to a bracket delivery cue; it does not claim exact phrase scoping. Unbalanced internal span controls are omitted while their words remain.

Fish S2.1 uses square brackets and accepts natural-language descriptions. Older `(happy)` examples on some Fish pages are S1 syntax. PETEY does not translate arbitrary parentheses or square brackets into directions. Delivery behavior is model-generated and should be auditioned with the selected voice.

## Streaming

With **Stream Fish speech** enabled, PETEY requests 24 kHz mono PCM16 from the hosted `/v1/tts` endpoint using HTTP streaming. The server forwards chunks through its existing authenticated NDJSON speech route; the desktop/mobile browser schedules PCM playback before the entire clip finishes. The selected model is always sent explicitly in the `model` header, and the voice is sent as `reference_id`.

Desktop automatic speech submits complete segments while chat text is arriving, and then speaks the remaining text. Mobile browser automatic speech keeps its single-request behavior after the reply, while audio itself streams. This is HTTP audio streaming with sentence buffering, not a persistent token-input Fish WebSocket or a speech-to-speech session.

Mute, Stop, and normal voice interruption abort the browser stream, stop scheduled audio, and close the upstream HTTP response. A failed Fish stream is reported without automatically replaying its already-spoken prefix or switching providers. Fish credentials remain server-side.

With streaming disabled, manual speech and automatic browser speech use the existing queued MP3 path. The native Android companion's existing speech-job API continues to use queued MP3; this change does not add a native Android streaming player. Both paths preserve Fish expression cues.

Automatic provider selection remains Gemini followed by OpenAI. Choosing Fish is explicit. The Create page's deAPI/Gemini audio-generation providers remain separate from conversational speech.

## Privacy and validation

Speech text, delivery cues, and the selected voice ID go to Fish Audio. Keys remain in local private settings and are never returned by public settings endpoints. Memory and persona management remain local.

Run:

```bash
../.peteydesktop/bin/python -m unittest tests.test_fish_tts
../.peteydesktop/bin/python tests/browser/fish_voice_regressions.py
```

Browser checks use temporary state, mocked APIs, and synthetic PCM. They cover visibility at desktop/phone widths, preservation of ordinary brackets/links, early playback, and cancellation. They do not prove live Fish account access, model expressiveness, actual latency, or physical-device audio routing.

References: [Models](https://docs.fish.audio/developer-guide/models-pricing/models-overview), [S2 emotion control](https://docs.fish.audio/developer-guide/core-features/emotions), [TTS API](https://docs.fish.audio/api-reference/endpoint/openapi-v1/text-to-speech), [Streaming](https://docs.fish.audio/features/realtime-streaming), [Drama 3 word controls](https://docs.fish.audio/features/text-to-speech/drama-3).


## Browse voices

Personality & voice now includes a searchable Fish Audio voice picker. Choose
**Public voices** or **My voices**, search by title, and use Previous/Next to browse
pages of 50. Select a named voice and save the Petey profile as usual. Browsing never
changes the saved voice automatically. A saved voice outside the current result page
stays available as Current voice; the Voice ID (manual) section remains available.

The catalog uses Fish's authenticated `GET https://api.fish.audio/model` endpoint,
with the existing saved Fish key or `FISH_API_KEY`, fixed upstream origin, bounded
responses, and no redirects. The browser receives only voice IDs/names, author
names, languages, and pagination. Loading/searching lists does not synthesize speech.
Catalog failures preserve the current voice and show a retryable error.

Reference: [Fish Audio List Models](https://docs.fish.audio/api-reference/endpoint/model/list-models).
