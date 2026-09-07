# Memory, Knowledge, and Privacy

PETEY stores conversations and knowledge locally in SQLite. Semantic retrieval can
use a local, Gemini, or OpenAI-compatible embedding model.

## Memory

PETEY uses recent chat history and can retrieve relevant details from other saved
conversations. Configure the embedding provider and model under
**Settings → Models & API keys → Memory search**.

Changing an embedding provider, model, or vector dimension can require rebuilding
stored embeddings. Use **Memory & privacy** to inspect storage and remove saved data.

## Knowledge

Open **Settings → Knowledge** to add reference documents, test retrieval, and rebuild
the knowledge index. Knowledge is useful for lore, project notes, character sheets,
manuals, and other material PETEY should reference.

## Temporary mode

Temporary conversations bypass memory reads and writes, including media-memory
records, while keeping their current history in the open window. They can still
contact providers and use tools.

## Where data is stored

The default application-data folder is:

- Linux: `$XDG_DATA_HOME/petey` or `~/.local/share/petey`
- macOS: `~/Library/Application Support/Petey`
- Windows: `%LOCALAPPDATA%\Petey`

Set `PETEY_DATA_DIR` to use another location. The data folder contains installation
identity, settings, the SQLite memory database, and generated Gallery files.

## What leaves the computer

Hosted providers receive the prompts, relevant memory or knowledge text, selected
Workspace context, attachments, audio, or generation instructions required for the
feature being used. Local-provider mode keeps its chat or embedding request on the
configured local endpoint. Media-generation requests go to deAPI.

Never include API keys, private chat content, or sensitive files in public issue
reports.
