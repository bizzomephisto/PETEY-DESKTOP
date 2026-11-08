# TTIK visual mode

TTIK replaces Neural Core with an original three-column red segmented voice
display, a clipped-corner dark housing, and a small microphone scope.

Restart PETEY after updating its source, open Visual Mode, and select **TTIK**
under **Animation**. Existing saved Neural Core selections migrate to TTIK;
other animation selections remain as saved. Desktop and mobile use the same renderer.

The red lamps follow the amplitude of PETEY's audible voice output. Both queued
speech (including Fish Audio) and streamed PCM share the existing playback bus
through an AnalyserNode. The center column extends farther than the side columns;
silent output settles back to two dim standby lamps. There is no simulated speech
pulse in TTIK. The other visual modes retain their existing behavior.

The lower waveform shows microphone PCM from the existing capture callback.
It uses a bounded 128-sample display buffer, never an additional microphone stream.
Muted, stopped, or stale microphone capture produces a flat trace. Microphone
activity does not illuminate the voice-output columns. The display buffer stays
in browser memory and does not add any audio uploads or change wake/STT behavior.

The housing, segments, bevels, glow, and waveform are Canvas 2D drawing code in
`web/static/ttik.js`; no generated bitmap frame or external assets are required.
It scales with the available canvas, supports high-DPI screens, respects the
existing reduced-motion frame rate, and places status/controls beside the module
in short landscape views.

Validation: 114 focused Desktop/state/settings/API tests passed. Browser checks
covered six sizes from 320×568 to 1920×1080, signal-driven light changes, silent
output, live/muted waveform, saved selection, switching back to Synapse, and
reduced motion. No JavaScript errors or transcription requests occurred in the
isolated preview. The preview screenshot uses test audio, not a live model reply.
Physical microphone and live provider playback were not exercised.
