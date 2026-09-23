# PETEY Mobile With a Permanent Cloudflare Tunnel

This guide connects PETEY Desktop to a permanent web address through a regular Cloudflare account on the free tier. It uses a **named Cloudflare Tunnel**, not a temporary `trycloudflare.com` Quick Tunnel.

The examples use:

```text
https://meetpetey.com
```

If another website already uses `meetpetey.com`, use a subdomain such as `petey.meetpetey.com` instead. Whichever hostname you choose in Cloudflare must exactly match PETEY's `--cloudflare-hostname` value.

## Cost and requirements

Cloudflare Tunnel is available on Cloudflare's free plan. To publish PETEY at a permanent hostname, Cloudflare requires:

- A free Cloudflare account.
- A domain you own, such as `meetpetey.com`.
- The domain added to Cloudflare and using Cloudflare's nameservers.
- The PETEY computer connected to the internet.

Cloudflare's free account does **not** include a free registered domain. Domain registration is separate. If `meetpetey.com` is already registered and active in your Cloudflare account, no additional domain work is required.

No router port forwarding, public IP address, or inbound firewall rule is needed. The `cloudflared` service makes an outbound connection from the PETEY computer to Cloudflare.

## How the finished setup works

After setup:

1. Linux starts `cloudflared` automatically in the background.
2. You start PETEY from the application menu.
3. PETEY listens locally on port `8765`.
4. Cloudflare sends `https://meetpetey.com` traffic through the tunnel to `http://localhost:8765`.
5. PETEY still requires its private mobile pairing link before a browser can enter.

The hostname remains the same through restarts.

## Using the same domain for PETEY at another house

You can run another independent PETEY installation at a subdomain such as:

```text
https://mbo.meetpetey.com
```

Use the same Cloudflare account and the existing `meetpetey.com` domain, but create a **separate named tunnel for each computer**. For example:

| PETEY installation | Cloudflare tunnel | Public hostname | Local service |
|---|---|---|---|
| Your computer | `petey-desktop` | `meetpetey.com` | `http://localhost:8765` |
| MBO computer | `petey-mbo` | `mbo.meetpetey.com` | `http://localhost:8765` |

Do not install your original `petey-desktop` tunnel token on the MBO computer. Installing one tunnel token on computers in two houses creates replicas of the same tunnel and can send requests to the wrong computer. Create `petey-mbo` in the Cloudflare dashboard and install only its newly generated token on the MBO computer.

On the MBO computer:

1. Install PETEY and `cloudflared` using this guide.
2. In **Cloudflare Dashboard → Networking → Tunnels**, create a new tunnel named `petey-mbo`.
3. Copy the installation command generated for `petey-mbo` and run it on the MBO computer.
4. Add a published application route to that tunnel with:

```text
Hostname:    mbo.meetpetey.com
Service:     HTTP
Service URL: http://localhost:8765
```

5. Install Dad's PETEY menu shortcut with:

```bash
cd '/path/to/PETEY_DESKTOP'

.venv/bin/python run_desktop.py \
  --install-shortcut \
  --cloudflare \
  --cloudflare-hostname 'mbo.meetpetey.com' \
  --port 8765
```

Replace `/path/to/PETEY_DESKTOP` with the actual PETEY project folder on the MBO computer.

When PETEY launches on that computer, it prints a private link resembling:

```text
https://mbo.meetpetey.com/?access_token=MBO_PRIVATE_PETEY_TOKEN
```

Open that complete link on the intended phone. The MBO PETEY installation has its own data, settings, tunnel token, and mobile pairing token. Your installation at `meetpetey.com` remains separate, and both can run simultaneously.

## 1. Create or sign in to the Cloudflare account

Open:

<https://dash.cloudflare.com/>

Sign in or create an account. Select the **Free** plan when Cloudflare asks you to choose a plan.

## 2. Add the domain to Cloudflare

Skip this section if `meetpetey.com` already appears as **Active** in the Cloudflare dashboard.

1. In the Cloudflare dashboard, select **Add a domain** or **Onboard a domain**.
2. Enter `meetpetey.com` without `https://` or a path.
3. Select the **Free** plan.
4. Review the DNS records Cloudflare discovers.
5. Cloudflare will display two assigned nameservers.
6. Sign in to the company where the domain was registered.
7. Replace the existing authoritative nameservers with the two nameservers supplied by Cloudflare.
8. Return to Cloudflare and wait for the domain status to become **Active**.

Nameserver activation can take some time. Do not continue until Cloudflare shows the domain as active.

## 3. Open the PETEY project folder

The following commands use this PETEY installation:

```bash
cd '/mnt/projects1/PROJECT_MASTER_FOLDER/projects/PETEY_DESKTOP_LOCALALAMAK'
pwd
```

The final command should print:

```text
/mnt/projects1/PROJECT_MASTER_FOLDER/projects/PETEY_DESKTOP_LOCALALAMAK
```

## 4. Prepare PETEY's Python environment

If PETEY already runs from `.venv`, it is safe to run the dependency command again:

```bash
cd '/mnt/projects1/PROJECT_MASTER_FOLDER/projects/PETEY_DESKTOP_LOCALALAMAK'

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi

.venv/bin/python -m pip install -r requirements.txt
```

## 5. Install `cloudflared`

First check whether it is already installed:

```bash
cloudflared --version
```

If that prints a version, continue to step 6.

For a 64-bit Intel or AMD Ubuntu, Pop!_OS, Linux Mint, or Debian computer, run:

```bash
cd /tmp
curl -L --output cloudflared-linux-amd64.deb \
  'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb'
sudo apt install ./cloudflared-linux-amd64.deb
cloudflared --version
```

You can check the computer architecture with:

```bash
uname -m
```

If it does not print `x86_64`, download the matching package from Cloudflare's official download page:

<https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/>

## 6. Create PETEY's named tunnel

In the Cloudflare dashboard:

1. Open **Networking**.
2. Open **Tunnels**.
3. Select **Create a tunnel**.
4. Choose **Cloudflared** if Cloudflare asks for the connector type.
5. Name the tunnel `petey-desktop`.
6. Select **Create tunnel**.
7. Under the connector setup, select **Linux** and the correct computer architecture.

Cloudflare will display an installation command containing a long private tunnel token. It will resemble:

```bash
sudo cloudflared service install eyJ...LONG_PRIVATE_TUNNEL_TOKEN...
```

Copy the exact command from your Cloudflare dashboard and run it on the PETEY computer. Do not use the example token above.

The tunnel token is a secret. Do not paste it into chat, documentation, screenshots, or Git commits.

After running Cloudflare's command, verify the service:

```bash
sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared --no-pager
```

The status should show `active (running)`. Return to the Cloudflare dashboard and wait for the connector to show **Connected** or the tunnel to show **Healthy**. Then select **Continue**.

## 7. Route the permanent hostname to PETEY

Open the new `petey-desktop` tunnel in the Cloudflare dashboard, then:

1. Open the **Routes** tab.
2. Select **Add route**.
3. Select **Published application**.
4. Choose the public hostname.
5. Set the service type to **HTTP**.
6. Set the service URL to `localhost:8765` or `http://localhost:8765`, depending on how the form is displayed.
7. Save the route.

For the root hostname used in this guide:

```text
Hostname:    meetpetey.com
Service:     HTTP
Service URL: http://localhost:8765
```

If `meetpetey.com` already hosts another site, use:

```text
Hostname:    petey.meetpetey.com
Service:     HTTP
Service URL: http://localhost:8765
```

Cloudflare creates the required tunnel DNS record when the published application route is saved. Do not manually create a second conflicting DNS record for the same hostname.

The local service uses HTTP because it stays on the PETEY computer. The public mobile address uses HTTPS through Cloudflare.

## 8. Install PETEY in the Linux application menu

Use the exact hostname configured in the Cloudflare route. For `meetpetey.com`, copy and paste:

```bash
cd '/mnt/projects1/PROJECT_MASTER_FOLDER/projects/PETEY_DESKTOP_LOCALALAMAK'

PETEY_HOST='meetpetey.com'

.venv/bin/python run_desktop.py \
  --install-shortcut \
  --cloudflare \
  --cloudflare-hostname "$PETEY_HOST" \
  --port 8765
```

If you configured `petey.meetpetey.com`, change only this line:

```bash
PETEY_HOST='petey.meetpetey.com'
```

The installer creates or updates PETEY's per-user Linux application launcher and then exits. It saves these startup arguments in the launcher:

```text
--cloudflare --cloudflare-hostname meetpetey.com --port 8765
```

Search the Linux application menu for **PETEY** and open it.

Unlike a Quick Tunnel, this hostname is permanent. You do not need to reinstall the menu shortcut after restarting the computer.

## 9. Start PETEY directly from a terminal

The application-menu shortcut is recommended for normal use. To start PETEY directly, run:

```bash
cd '/mnt/projects1/PROJECT_MASTER_FOLDER/projects/PETEY_DESKTOP_LOCALALAMAK'

PETEY_HOST='meetpetey.com'

.venv/bin/python run_desktop.py \
  --cloudflare \
  --cloudflare-hostname "$PETEY_HOST" \
  --port 8765
```

Use `PETEY_HOST='petey.meetpetey.com'` instead if that is the hostname configured in Cloudflare.

PETEY's **Restart** button preserves the Cloudflare hostname and port from the current launch.

## 10. Pair the phone or tablet

When PETEY starts in Cloudflare mode, the terminal prints a private link similar to:

```text
https://meetpetey.com/?access_token=LONG_PRIVATE_PETEY_TOKEN
```

Open the entire link on the mobile device, including:

- `https://`
- The hostname
- `?access_token=`
- The complete token

The bare address `https://meetpetey.com` intentionally returns an authorization error until the browser is paired. This is PETEY's additional security layer and does not mean the tunnel is broken.

After a successful visit, PETEY stores a secure pairing cookie in that browser. Paired browsers normally remain authorized for one year unless mobile access is rotated.

Treat the private PETEY link like a password. Send it to your own device through a private method.

## 11. Add PETEY to an iPhone or iPad Home Screen

1. Open the complete private PETEY link in **Safari**.
2. Verify that PETEY loads.
3. Tap Safari's **Share** button.
4. Scroll down and select **Add to Home Screen**.
5. Name it **PETEY**.
6. Tap **Add**.

Because this setup uses a permanent hostname, the Home Screen icon continues to work after restarting PETEY, `cloudflared`, or the computer.

For voice and webcam features, allow Safari or Chrome to use the microphone and camera when prompted. Cloudflare provides the HTTPS connection required by mobile browsers for these permissions.

## 12. Normal daily use

After a reboot, confirm that the tunnel service is running:

```bash
systemctl is-active cloudflared
```

The expected response is:

```text
active
```

Then open **PETEY** from the Linux application menu. There is no separate tunnel terminal to keep open because `cloudflared` runs as a system service.

Useful service commands:

```bash
sudo systemctl status cloudflared --no-pager
sudo systemctl restart cloudflared
sudo journalctl -u cloudflared --no-pager -n 100
```

## 13. Test the hostname

With PETEY running, test the permanent address from the PETEY computer:

```bash
curl -i 'https://meetpetey.com/'
```

A PETEY `401 Unauthorized` response mentioning the private link is a successful tunnel test. It proves that Cloudflare reached PETEY while PETEY correctly refused an unpaired request.

If you use the subdomain, test it instead:

```bash
curl -i 'https://petey.meetpetey.com/'
```

## 14. Rotate PETEY's private mobile access

If the private PETEY pairing link was exposed, close PETEY and run it once with `--rotate-mobile-access`:

```bash
cd '/mnt/projects1/PROJECT_MASTER_FOLDER/projects/PETEY_DESKTOP_LOCALALAMAK'

PETEY_HOST='meetpetey.com'

.venv/bin/python run_desktop.py \
  --cloudflare \
  --cloudflare-hostname "$PETEY_HOST" \
  --port 8765 \
  --rotate-mobile-access
```

PETEY creates and prints a new private pairing link. Previously paired browsers must use the new link.

This rotates PETEY's mobile pairing secret. It does not change the separate Cloudflare tunnel token.

## 15. Optional Cloudflare Access login

PETEY already protects the site with its private pairing link. You can add Cloudflare Access as another login layer without purchasing an Access subscription for ordinary personal use on the free plan.

In Cloudflare Zero Trust:

1. Open **Access** and then **Applications**.
2. Add a **Self-hosted** application.
3. Enter the same PETEY hostname.
4. Create an **Allow** policy for your email address or chosen identity provider.
5. Save and test it in a private browser window.

Do this only after the basic tunnel and PETEY pairing flow work. PETEY's private pairing requirement remains active behind Cloudflare Access.

## Troubleshooting

### The tunnel is Healthy, but the page shows Bad Gateway

PETEY is probably not running on port `8765`. Start PETEY from the application menu or run:

```bash
cd '/mnt/projects1/PROJECT_MASTER_FOLDER/projects/PETEY_DESKTOP_LOCALALAMAK'
.venv/bin/python run_desktop.py \
  --cloudflare \
  --cloudflare-hostname 'meetpetey.com' \
  --port 8765
```

Check the local port with:

```bash
ss -ltn | grep ':8765'
```

### PETEY says phone access requires the private link

The tunnel is working. Open the complete tokenized link printed when PETEY starts, not only the hostname.

### Cloudflare reports that a DNS record already exists

The chosen hostname already has an A, AAAA, or CNAME record. If it belongs to another site, keep it and publish PETEY at `petey.meetpetey.com`. If it is an obsolete PETEY record, remove the obsolete record before saving the tunnel route.

### The tunnel is Inactive or Down

Run:

```bash
sudo systemctl restart cloudflared
sudo systemctl status cloudflared --no-pager
sudo journalctl -u cloudflared --no-pager -n 100
```

Also verify that the computer can make outbound connections to Cloudflare. Restrictive networks must allow the connector to reach Cloudflare on port `7844`.

### The Cloudflare route works, but the PETEY menu shortcut uses the wrong hostname

Reinstall the shortcut with the exact published hostname:

```bash
cd '/mnt/projects1/PROJECT_MASTER_FOLDER/projects/PETEY_DESKTOP_LOCALALAMAK'
.venv/bin/python run_desktop.py \
  --install-shortcut \
  --cloudflare \
  --cloudflare-hostname 'meetpetey.com' \
  --port 8765
```

### Microphone or webcam access does not appear

1. Confirm the page begins with `https://`.
2. Open the site's permissions in Safari or Chrome.
3. Allow microphone and camera access.
4. Reload PETEY after changing permissions.
5. Test the private PETEY link in a normal browser tab before testing the Home Screen application.

## Security notes

- Do not open ports on the router for this setup.
- Do not share the Cloudflare tunnel token.
- Do not share PETEY's complete private pairing link.
- The bare hostname remains protected by PETEY's pairing gate.
- `cloudflared` uses an outbound-only connection, so the PETEY computer does not need a public IP address.
- Rotate PETEY mobile access if its private link is exposed.
- Rotate the Cloudflare tunnel token from the Cloudflare dashboard if that separate token is exposed.

Official references:

- [Create a remotely managed tunnel in the Cloudflare dashboard](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/)
- [Cloudflare Tunnel setup and requirements](https://developers.cloudflare.com/tunnel/get-started/)
- [`cloudflared` downloads](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/)
- [Cloudflare tunnel tokens](https://developers.cloudflare.com/tunnel/reference/tunnel-tokens/)

PETEY's general remote-access documentation is at [`docs/wiki/Mobile-and-Remote-Access.md`](docs/wiki/Mobile-and-Remote-Access.md).
