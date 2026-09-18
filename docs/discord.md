# Discord bridge

PETEY can join one Discord server channel through an official Discord bot account.
The bot uses PETEY's selected personality and chat model, follows channel activity,
offers occasional games or made-up trivia, and accepts private instructions from
the desktop app. Discord displays the account with an **APP** badge.

## Set up the bot

1. Open **Discord** in PETEY's sidebar and choose **Open Discord Developer Portal**.
2. Create an application, open its **Bot** page, and set its username and avatar.
3. Under **Privileged Gateway Intents**, enable **Message Content Intent**. This is
   needed for PETEY to understand ordinary channel conversation. Larger verified
   bots may need Discord's approval for this intent.
4. On the Bot page, reset or copy the bot token. Paste it into PETEY and choose
   **Save and inspect bot**. Treat this token like a password.
5. Choose **Add PETEY to a Discord server**, select a server you can manage, and
   authorize the requested permissions.
6. Return to PETEY, refresh the server list, select a server and text channel, and
   choose **Connect**.

The generated invite requests Discord's **Administrator** permission. Discord
defines this as all permissions with channel-overwrite bypass. If PETEY is already
installed, use **Add PETEY to a Discord server** again or grant its role
Administrator in Discord for the new permission to take effect.

If Discord denies a server action, open **Server Settings → Roles**, select PETEY's
bot role, and enable **Manage Channels** for channel creation/deletion or **Manage
Messages** for cleanup. **Administrator** includes these permissions. A channel or
category permission override can still block a non-Administrator role.

PETEY supports three owner-only server actions: creating a text channel, deleting
the currently selected channel, and clearing up to 100 recent messages from that
channel. Enter the request in **Give PETEY an instruction**, review the proposal,
then approve or reject it. Public Discord messages are never treated as server
commands. PETEY does not expose kick, ban, member-prune, role-management, category,
or server-deletion operations.

Examples:

- `create a channel named linux`
- `create a new channel called talkytalk`
- `delete this channel`
- `clear this channel's last 50 messages`

Discord does not allow bulk deletion of messages older than 14 days. PETEY uses a
more conservative 13-day cutoff and reports how many eligible messages it removed.

The token is stored in PETEY's local settings file, whose permissions are restricted
to the local user where supported. It is never returned by the local API or placed in
the page. `DISCORD_BOT_TOKEN` may be used instead; a saved token takes precedence.
Clearing a saved token does not change an environment token.

## Conversation behavior

The Discord bridge uses activity-aware pacing and bounded room-only context:

- It ignores existing history at connection time and listens for a minute before
  contributing on its own. Direct mentions, replies to PETEY, PETEY's name, watched
  topics, and owner instructions bypass that initial listening period.
- Three new human messages can prompt an unsolicited contribution. In Auto, direct
  messages normally become eligible after 2–4 seconds and Discord is checked every
  four seconds. When several lines arrive together, PETEY prioritizes the newest
  addressed line or follow-up.
- After PETEY answers someone, that person's messages remain part of the same
  conversation for three minutes. They do not need to mention PETEY on every line.
  Messages from other people are not automatically attached to that exchange.
- A quiet channel gets at most one gentle invitation after roughly 60–70 minutes.
- Made-up trivia is introduced as invented, keeps one answer per round, and stops
  when people decline or do not engage.
- Messages are one line and at most 280 characters. Discord mentions are disabled
  on outgoing messages, so model text cannot ping users, roles, or `@everyone`.
- Messages from other bots and webhooks are ignored to prevent automated loops.
- Discord shows its native typing indicator as soon as PETEY starts generating a
  reply. PETEY refreshes it every eight seconds during a long model response. A
  failed typing pulse does not discard the reply.

Use **Give PETEY an instruction** for guidance such as “Offer a round of made-up
trivia” or “Stop offering games and talk about movies.” Later instructions override
earlier conflicting guidance. **Pause PETEY** keeps reading but suppresses replies;
**Disconnect** stops polling. Turn on **Auto-connect** to have PETEY reconnect at
app startup to the last server and channel it successfully joined. The saved token
must still be available. Turning the switch off leaves the last location saved but
stops startup reconnection.

## Watched topics and spontaneous participation

Add up to 20 comma-separated words or phrases under **Watched topics**. Matching is
case-insensitive and uses complete word or phrase boundaries, so `linux` matches
“Linux” but not an unrelated longer word. A new matching message is treated like a
direct message: it can bypass the initial listening period and five-minute message
ceiling, and becomes eligible within two seconds. PETEY remains silent when the
model decides that no safe or sensible public reply is useful; the internal pass
signal is never posted to Discord.

The slider controls spontaneous participation in conversations that do not mention
PETEY and contain no watched topic. PETEY considers an unsolicited response after
three new human messages, then the model decides whether it has a useful contribution.

## Room prompt

The editable **Room prompt** on the Discord screen defines PETEY's group-chat
behavior, response style, game rules, silence behavior, and public-chat boundaries.
It is stored locally with the Discord settings. Saving it updates the active bridge
for the next model reply; reconnecting is unnecessary. **Restore default** replaces
the customized text with PETEY's built-in room prompt. The selected Personality is
still applied before this room-specific prompt.

**AI enhance** sends the current draft to the selected chat model and replaces the
editor text with its suggested revision. Review the draft and choose **Save room
prompt** to apply it; enhancement does not save automatically. This uses the active
provider and can incur that provider's normal usage charge.

The **Spontaneous participation** slider is saved locally and can be changed while PETEY is
connected:

| Setting | Unsolicited conversation | Five-minute ceiling | Quiet invitation |
| --- | ---: | ---: | ---: |
| Auto | 8–30 seconds based on channel activity | 6–8 | 60–70 minutes |
| Relaxed | 60 seconds | 3 | 90–120 minutes |
| Balanced | 35 seconds | 5 | 60–80 minutes |
| Lively | 18 seconds | 7 | 45–60 minutes |
| Fast | 8 seconds | 8 | 30–45 minutes |

These are eligibility delays before model generation; network and model response
time are additional. The four-second Discord polling interval also bounds how soon
PETEY sees a new message. Direct questions and watched topics use a delay of at most
two seconds regardless of the slider.

Channel context and instructions remain in memory only for the current connection.
They do not read or write PETEY's personal chat memory and cannot use desktop tools.
Messages are sent to the configured model provider to generate replies.

PETEY polls Discord's official HTTPS API every four seconds. If access is denied,
the channel disappears, or delivery is uncertain, the bridge stops rather than
automatically replaying a message. Discord's API rate-limit response may cause one
bounded retry after the server-specified delay.

While connected, PETEY also maintains a Discord Gateway session, identifies with an
explicit online presence, sends Discord heartbeats, and reconnects after transient
Gateway disconnects. Disconnecting PETEY closes that session and returns the bot to
offline.

Automating a normal Discord user account is not supported. Discord classifies that
as a prohibited self-bot; only a bot token is accepted by this bridge.

## Media slash commands

When PETEY connects, it creates or updates these server commands and preserves other
commands registered to the application:

- `/genimg`, `/img2img`
- `/genvid`, `/img2vid`, `/vid2vid`
- `/genmusic`, `/tts`
- `/rmbg`, `/upscale`

The commands use the API keys, selected models, speech settings, queue, and local
Gallery from the running PETEY Desktop app. Image/video editing commands accept a
Discord attachment up to 25 MB. PETEY acknowledges the command immediately, updates
the Discord response when the background job finishes, and saves completed media to
the desktop Gallery. PETEY Desktop must remain running and connected while commands
are used. Slash commands are explicit paid generation requests; anyone allowed to
use them in that Discord server can consume the configured deAPI account balance.
