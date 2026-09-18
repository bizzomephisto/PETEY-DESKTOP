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

Discord is the only add-on built into the PETEY source release. Home Assistant,
Blender, and every other external integration are installed separately and are not
included in PETEY's GitHub archive.

Developers can read the repository's [add-on authoring contract](../addons.md).
