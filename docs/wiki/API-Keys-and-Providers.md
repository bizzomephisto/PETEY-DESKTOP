# API Keys and Providers

An API key connects PETEY to your account with a provider. You need keys only for
the services you use. Save keys under **Settings → Models & API keys → API keys**.
Keep them out of chat messages, screenshots, issue reports, and source control.

## Google Gemini

Gemini can power chat, image inspection, spoken replies, transcription, and memory
embeddings.

- [Create or view a Gemini API key](https://aistudio.google.com/apikey)
- [Official Gemini API-key guide](https://ai.google.dev/gemini-api/docs/api-key)

When Gemini is the chat provider, image attachments follow the selected Gemini
chat model. OpenAI and local chat still use the configured Gemini model to describe
image attachments.

## OpenAI

OpenAI can power chat, spoken replies, and memory embeddings.

- [Create an OpenAI API key](https://platform.openai.com/api-keys)
- [Official OpenAI developer quickstart](https://developers.openai.com/api/docs/quickstart)

An API key is separate from a ChatGPT subscription. Check your OpenAI Platform
billing, model access, usage limits, and current pricing.

## deAPI

deAPI powers PETEY's media generation and its default microphone transcription.

- [Open the deAPI dashboard](https://app.deapi.ai/)
- [Official deAPI quickstart](https://docs.deapi.ai/quickstart)

In the deAPI dashboard, open **Settings → API Keys** and create a secret key. Media
jobs consume account credits; PETEY shows the balance and estimates supported jobs.

## Local models

PETEY supports OpenAI-compatible local servers such as LM Studio and Ollama.

1. Start the local server and load a model.
2. Choose **Local** under **Chat & vision**.
3. Enter the server URL. PETEY includes common LM Studio and Ollama presets.
4. Load or enter a model, save the provider, and test the connection.

Local chat keeps that model request on the configured endpoint. Image inspection
still needs Gemini. A local embedding endpoint can be configured separately for
memory search.

## Environment variables

PETEY also recognizes:

```text
GEMINI_API_KEY
OPENAI_API_KEY
LOCAL_AI_API_KEY
DEAPI_KEY
```

A key saved in Settings takes precedence over its environment variable. PETEY's
public settings endpoints return key status, never the key values.
