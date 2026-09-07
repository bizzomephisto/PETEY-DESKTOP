# Voice and Microphone

Speech output and microphone transcription use separate settings from chat.

## Spoken replies

1. Open **Settings → Models & API keys → Spoken replies**.
2. Choose Automatic, Gemini, OpenAI, or Disabled and save the speech provider.
3. Open **Personality & voice** to choose PETEY's voice, delivery directions, and
   whether new replies should play automatically.
4. Use the Speak control on an individual reply whenever you want manual playback.

Automatic speech tries Gemini and can fall back to OpenAI when configured. The
required provider key must be saved or present in the environment.

## Microphone

Open **Settings → Microphone** to choose an input device and listening mode:

- Push-to-talk
- Continuous listening
- Wake-name mode

Allow microphone access when your system asks. Space can be used for push-to-talk
when the feature is active and focus is not inside a text field.

## Transcription

The default automatic transcription path uses deAPI and falls back to Gemini when
available. You can choose Gemini directly under **Models & API keys**. Completed
utterance clips are sent to the selected transcription provider and are not stored
in PETEY's gallery or memory.

If voice is not working, verify the separate speech and transcription settings,
provider keys, selected microphone, system input level, output volume, and operating
system permissions.
