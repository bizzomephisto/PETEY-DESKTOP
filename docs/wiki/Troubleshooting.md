# Troubleshooting

## Chat does not respond

1. Confirm the key is saved for the selected provider.
2. Save the provider and model again.
3. Select **Test connection**.
4. Check the provider error, model access, quota, billing, and current service status.

PETEY retries once through the normal response endpoint when a live response stream
is interrupted. A repeated error usually indicates a provider or network problem.

## Image attachments fail

Image inspection always needs a Gemini key and valid Gemini model, including when
OpenAI or a local model handles chat.

## Voice or microphone fails

Check the separate chat, spoken-reply, and transcription providers. Verify the
appropriate keys, selected input device, system volume, microphone level, and OS
permissions.

## Media does not start

Confirm the deAPI key, balance, operation inputs, selected model, and its current
parameter limits. A model appearing in the catalog does not guarantee account access.

## Local provider cannot connect

Start the local server, load a model, and confirm its OpenAI-compatible base URL.
Common defaults are `http://localhost:1234/v1` for LM Studio and
`http://localhost:11434/v1` for Ollama.

## PETEY does not open from the Linux menu

Activate PETEY's current environment from the current project folder and reinstall
the shortcut:

```bash
source .venv/bin/activate
python run_desktop.py --install-shortcut
```

## Reporting a problem

[Open a GitHub issue](https://github.com/bizzomephisto/PETEY-DESKTOP/issues) with:

- PETEY's version
- Your operating system
- The provider and model name, when relevant
- Steps to reproduce the problem
- The exact error message

Remove API keys, personal chats, private filenames, and sensitive documents first.
