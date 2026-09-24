# Getting Started

Start with one chat provider. Add the other services only when you want them.

## First conversation

1. Get a Gemini or OpenAI key from [API Keys and Providers](API-Keys-and-Providers),
   or start a local OpenAI-compatible model server.
2. Open **Settings → Models & API keys → API keys**.
3. Paste the key into its provider field and select **Save key**.
4. Open **Chat & vision**, choose the provider and model, and select **Save provider**.
5. Select **Test connection**. This sends a small generation request to the provider.
6. Open Chat and send a message. Enter sends; Shift+Enter inserts a new line.

## Useful next steps

- Set PETEY's character and tone under **Personality & voice**.
- Configure spoken replies and your microphone in [Voice and Microphone](Voice-and-Microphone).
- Add reference documents under **Knowledge**.
- Use **Temporary** for a conversation that should not read or write saved memory.
- Save a deAPI key before using **Media**.
- Add an approved folder under **Settings → Tools & integrations** before using the Filesystem connector.

API keys, model choices, speech, transcription, and memory search are separate
settings. A working chat connection does not automatically configure every other
feature.

## Quick PETEY on COSMIC

Install the cursor popup hotkey once from the PETEY folder:

```bash
python run_desktop.py --install-quick-hotkey
```

Press **Super+F1** to open Quick PETEY beside the mouse pointer. Its message box
is focused immediately. Enter sends, Shift+Enter adds a line, and Escape closes
the popup. Hold Space while the empty message box is focused to talk. The Screen,
Window, and File buttons attach context to the next message; Window opens the
COSMIC screenshot picker.

## Open PETEY on a phone

Put the phone and computer on the same trusted network and start a dedicated LAN
session from the PETEY project folder:

```bash
python run_desktop.py --lan
```

Open the complete private link printed in the terminal. PETEY listens on port
`8765` by default; use `--port 9000` to choose another. Keep the link private
because it grants access to the running session. If it does not open, allow the
port through the computer firewall and check that the Wi-Fi router does not use
client isolation. Mobile microphone capture may require HTTPS and can be
unavailable in this local HTTP mode.
