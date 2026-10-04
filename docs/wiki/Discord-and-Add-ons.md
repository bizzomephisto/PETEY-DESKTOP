# Discord and Add-ons

## Connect the built-in Discord bot

Open **Discord** in PETEY's sidebar and follow its numbered setup guide. Create a
bot in the Discord Developer Portal, enable Message Content Intent, save the bot
token in PETEY, invite the bot to a server, and select a text channel. PETEY must
remain running while the bot is connected.

Direct mentions, replies, conversational follow-ups, and watched topics receive
priority. The participation setting controls unsolicited room messages. Discord
uses its own editable room prompt and does not read PETEY's desktop conversation
memory or tools.

Media slash commands use the deAPI key and model selections saved in PETEY. Their
results also enter the local Gallery. Channel creation, selected-channel deletion,
and recent-message cleanup appear as proposals that the owner must approve inside
PETEY.

See the repository's [complete Discord guide](../discord.md) for permissions,
commands, privacy, and troubleshooting.

## Install an external add-on

Open **Add-ons**, select **Open add-ons folder**, and copy the add-on's complete
folder there. Enable it in PETEY and restart the app. Add-ons run local Python code
with the same user permissions as PETEY, so install only code you trust.

Discord and Tasks are built into the PETEY source release. Home Assistant,
Blender, and every other external integration are installed separately and are not
included in PETEY's GitHub archive.

## Addons on GitHub

| Addon | What it adds |
| --- | --- |
| [Home Assistant MCP](https://github.com/bizzomephisto/PETEY-HOME-ASSISTANT) | Household entities, device controls, and alerts. |
| [Spotify](https://github.com/bizzomephisto/PETEY-SPOTIFY) | Spotify Connect playback, playlists, DJ mode, and a shared media player. |
| [OpenCode](https://github.com/bizzomephisto/PETEY-OPENCODE) | Start, monitor, preview, and cancel coding-agent runs. |
| [Google Sheets Scorecards](https://github.com/bizzomephisto/PETEY-GOOGLE-SHEETS) | Read configured sheets and fill golf scores from scorecard pictures. |
| [Quick Actions](https://github.com/bizzomephisto/PETEY-QUICK-ACTIONS) | Customizable silent action buttons for desktop and mobile. |

### Additional local addons

These addons are available in the development setup; they currently have no
published repository on this GitHub account. They are installed separately.

| Addon | What it adds |
| --- | --- |
| Blender MCP | Scene inspection and reviewed Blender script execution. |
| PETEY Webcam | Named cameras, visual questions, snapshots, and frame comparison. |
| PETEY Conference | Record, transcribe, search, and selectively participate in meetings. |
| Discord Voice & YouTube DJ | Wake-name voice conversations and a YouTube playback queue. |
| Freebuff | Set up, start, and track Freebuff coding-agent runs. |
| Real-Time Clock | Current-time tools and an analog/digital clock panel. |
| System Monitor | CPU, memory, load, uptime, and process information. |

Follow each repository's instructions. Where a release archive is available, extract its one
add-on folder into PETEY's add-ons directory, enable it, and restart PETEY.

Developers can read the repository's [add-on authoring contract](../addons.md).
