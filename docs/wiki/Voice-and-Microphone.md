# Voice and Microphone

Speech output and microphone transcription use separate settings from chat.

## Spoken replies

1. Open **Settings → Personality & voice**.
2. Choose Automatic, Gemini, OpenAI, or Disabled, then choose PETEY's voice,
   delivery directions, and whether new replies should play automatically.
3. Select **Save Petey profile**. Instructions, traits, communication style, voice,
   and speech provider save together.
4. Use **Models & API keys → Speech models** only when you want to change the model
   used by Gemini or OpenAI speech.
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

### Wake acknowledgements

In wake-name mode, PETEY runs a small local keyword model against the microphone
stream. It can acknowledge “Petey” or “Hey Petey” without waiting for cloud
transcription or starting the browser's separate speech recognizer. The first use
downloads about 17 MB of model files; later sessions load them from the local PETEY
data folder. Cloud transcription still handles the actual request and remains the
fallback if local detection is unavailable.

The acknowledgement waits briefly for a pause. Saying only “Petey” plays a canned
response and keeps listening; continuing directly into “Petey, turn off the lights”
cancels the pending cue and sends the command without an interruption.

Open **Settings → Microphone → Open cue folder** to customize acknowledgements. Put
short audio files directly in the folder named for the current speech voice, such as
`voice-cues/Kore/` or `voice-cues/marin/`.

PETEY creates `default/` plus a ready-to-fill folder for every supported Gemini
voice. An OpenAI voice folder is created when that voice is selected. Folder names
match the voice names shown in **Personality & voice**.

PETEY randomly chooses WAV, MP3, OGG, OPUS, M4A, AAC, FLAC, or WEBM files from the
current voice folder. If that folder has no clips, it checks `voice-cues/default/`.
If both are empty, the browser speaks a built-in “Yeah?”, “What's up?”, or “Mm-hmm?”
acknowledgement. The desktop reloads clips when its window regains focus; a remote
browser can be reloaded after files are added.

## Transcription

The default automatic transcription path uses deAPI and falls back to Gemini when
available. You can choose Gemini directly under **Models & API keys**. Completed
utterance clips are sent to the selected transcription provider and are not stored
in PETEY's gallery or memory.

If voice is not working, verify the separate speech and transcription settings,
provider keys, selected microphone, system input level, output volume, and operating
system permissions.
