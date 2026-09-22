# Mobile and Remote Access

PETEY's mobile layout keeps the conversation, visual animation, saved Petey profile,
speech voice, microphone mode, animation picker, and fullscreen control available on a phone.
The chat header stays compact: choose the profile for the current conversation
from **Settings → Chat profile**. If Quick Actions is installed, tap **⚡** to show
its configured buttons and tap an action to close the menu.
Cloudflare supplies trusted HTTPS, so mobile browsers can grant microphone access
without installing PETEY's local certificate.

In Visual Mode, captions appear in the upper third of the screen and fade away
five seconds after a reply finishes. The mic,
push-to-talk, and speaker controls sit above PETEY at the bottom. A red X marks a
muted mic or speaker. Muting the mic stops an active recording or continuous
listening session. Tap **PETEY** beneath the chevron to show **Chat** on the left
and **Fullscreen** and **Settings** on the right; tap PETEY again to hide them.

Choose one of these setups:

- **Your own domain:** a stable address such as `petey.example.com`. This is the
  best everyday setup. The domain must use Cloudflare DNS, but Cloudflare Tunnel
  itself is available on the free plan.
- **Free temporary address:** a random `trycloudflare.com` address without an
  account or domain. It changes every time and is intended for testing.
- **Local Wi-Fi:** no Cloudflare account or Internet exposure. Use `--lan-https`
  and install PETEY's local certificate on the phone.

## Before you start

Install PETEY normally and verify that `python run_desktop.py` opens on the
computer. Install Cloudflare's `cloudflared` connector from the
[official downloads page](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/),
then check it from a terminal:

```bash
cloudflared --version
```

Cloudflare mode keeps PETEY's origin on loopback. Devices on the local network
cannot open port `8765` directly; all remote traffic arrives through the tunnel.
Do not combine `--cloudflare` with `--lan` or `--lan-https`.

## Stable address with your own domain

### 1. Create the tunnel

1. Sign in to the Cloudflare dashboard and open **Networking → Tunnels**.
2. Select **Create a tunnel**, choose Cloudflared, and name it `petey`.
3. Choose the computer's operating system and architecture.
4. Copy and run the connector installation command shown by Cloudflare. Keep the
   tunnel token private.
5. Wait until the connector status is **Healthy**, then continue.

The dashboard command normally installs `cloudflared` as a background service, so
the connector can stay online without a second terminal.

### 2. Add PETEY's public hostname

In the tunnel's **Routes** tab, add a **Published application**:

| Field | Value |
| --- | --- |
| Subdomain | `petey` or another name you want |
| Domain | Your domain in Cloudflare |
| Path | Leave empty |
| Service type | `HTTP` |
| Service URL | `localhost:8765` |

Save the route. The finished address will look like
`https://petey.example.com`. Cloudflare creates and manages the public HTTPS
certificate; PETEY's `--lan-https` certificate is not used for this setup.

### 3. Configure PETEY

Open PETEY's `.env` file and add the public hostname without `https://` or a path:

```dotenv
PETEY_CLOUDFLARE_HOSTNAME=petey.example.com
PETEY_CLOUDFLARE_PORT=8765
```

Start PETEY:

```bash
python run_desktop.py --cloudflare
```

PETEY opens on the computer and prints a private public URL containing its pairing
token. Open that complete HTTPS URL on the phone once and allow microphone access
when prompted. PETEY removes the token from the address and saves a one-year Secure,
HttpOnly browser cookie. The same phone and home-screen shortcut remain paired across
PETEY restarts, and PETEY prints the same private pairing link on later launches.

On Linux, make the normal PETEY application-menu icon start this mode:

```bash
python run_desktop.py --install-shortcut --cloudflare
```

Run the shortcut installer again without `--cloudflare` if you later want the
application icon to return to local-only mode.

### 4. Access protection and revocation

PETEY rejects the bare hostname with `401`, even if the Cloudflare route itself is
public. Keep the pairing link private. For a second layer, create a Cloudflare Access
self-hosted application for the PETEY hostname and allow only your email address or
chosen identity provider. After the Access login, PETEY works in the same browser tab.

If a phone is lost or the pairing link is exposed, stop PETEY and restart it with:

```bash
python run_desktop.py --cloudflare --rotate-mobile-access
```

PETEY creates a new private link. Old links and every existing PETEY pairing cookie
are rejected. Open the newly printed link on each phone you still trust.

## Free temporary Cloudflare address

Cloudflare Quick Tunnels create a random HTTPS address without an account, domain,
DNS changes, or tunnel token. They are intended for testing, have a 200 concurrent
request limit, do not support Server-Sent Events, and disappear when `cloudflared`
stops. PETEY streams chat over NDJSON rather than Server-Sent Events.

Open a terminal and start the free tunnel:

```bash
cloudflared tunnel --url http://localhost:8765
```

Copy the generated address, which looks like:

```text
https://random-words.trycloudflare.com
```

Leave that terminal running. In a second terminal, activate PETEY's environment
and start PETEY with the generated hostname:

```bash
source .venv/bin/activate
python run_desktop.py --cloudflare \
  --cloudflare-hostname random-words.trycloudflare.com \
  --port 8765
```

On Windows PowerShell, activate with `.venv\Scripts\activate` and put the PETEY
command on one line. Open the complete tokenized HTTPS URL printed by PETEY on the
phone. Stop both PETEY and `cloudflared` when finished.

The random tunnel address alone does not pass PETEY's pairing gate, but Quick Tunnels
cannot be configured with Cloudflare Access. Treat PETEY's printed pairing link like
a password: do not post it, reuse it in screenshots, or send it to someone you do
not trust.

Quick Tunnels may refuse to start when a `config.yaml` file exists in the local
`.cloudflared` directory. Rename that file temporarily or use the stable named
tunnel setup instead.

## Add PETEY to the phone's home screen

Open PETEY's complete private pairing link first, then:

- **Android Chrome:** open the three-dot menu and choose **Add to Home screen** or
  **Install app**.
- **iPhone or iPad Safari:** tap **Share**, choose **Add to Home Screen**, edit the
  name if desired, and tap **Add**.

The home-screen icon reopens the clean saved address using the browser's pairing
cookie. A stable custom domain continues to work across restarts. A free Quick
Tunnel icon becomes stale when the temporary URL changes.

### PETEY says the private link is required

- Open the complete `https://.../?access_token=...` link printed by the current
  PETEY installation, not only the bare hostname.
- Make sure the browser accepts cookies and is not using a temporary private tab.
- Pair again if browser data was cleared, the one-year cookie expired, or mobile
  access was rotated.

## Troubleshooting

### Cloudflare shows a bad gateway or cannot reach the origin

- Start PETEY with `--cloudflare` and keep it running.
- Confirm the route uses `HTTP` and `localhost:8765`, not HTTPS.
- Confirm `PETEY_CLOUDFLARE_PORT`, `--port`, and the route all use the same port.
- Do not start a second PETEY process on the same port.
- A Healthy tunnel confirms the connector reached Cloudflare; it does not prove
  that PETEY is running at the configured local service URL.

### The microphone is unavailable

- Open the `https://` Cloudflare address rather than the local `http://` origin.
- Allow microphone access in the phone browser's site permissions.
- Close another app that is holding the microphone, then reload PETEY.
- On iPhone or iPad, test in Safari. On Android, test in current Chrome.

### The page loads but PETEY does not speak

Remote access and speech output are separate. Check PETEY Desktop's
**Personality & voice** settings, the selected speech provider and key, provider
quota, the phone's media volume, and the browser's audio permission. Tap once in
the page if the browser is waiting for a user gesture before allowing playback.

### The custom domain works only while a terminal is open

The named connector is running interactively rather than as a system service.
Return to the tunnel's **Install and run a connector** instructions and install the
service command for the computer. PETEY itself must still be running.

## Official Cloudflare references

- [Create a remotely managed tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/)
- [Publish an application route](https://developers.cloudflare.com/cloudflare-one/networks/routes/add-routes/)
- [Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/)
