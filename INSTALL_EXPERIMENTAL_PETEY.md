# Clone and Install Experimental PETEY

This guide installs PETEY Desktop experimental release `v0.19.0-experimental.1` from GitHub and configures it for:

```text
https://mbo.meetpetey.com
```

The PETEY Desktop repository is private, so the computer must authenticate with GitHub before cloning it.

## 1. Install Git and GitHub CLI

On Ubuntu, Pop!_OS, Linux Mint, or another Debian-based system:

```bash
sudo apt update
sudo apt install git gh python3 python3-venv python3-pip
```

Verify the commands:

```bash
git --version
gh --version
python3 --version
```

## 2. Authenticate with GitHub

Run:

```bash
gh auth login
```

Choose:

```text
GitHub.com
HTTPS
Login with a web browser
```

GitHub CLI will display a one-time code. Open the displayed web address, enter the code, and approve access.

Verify authentication:

```bash
gh auth status
```

The authenticated GitHub account must have permission to read the private `bizzomephisto/PETEY-DESKTOP` repository.

## 3. Clone PETEY Desktop

Choose where PETEY should be installed. The following example installs it under the current user's home directory:

```bash
cd ~
git clone https://github.com/bizzomephisto/PETEY-DESKTOP.git
cd PETEY-DESKTOP
```

## 4. Check out the experimental release

Fetch the tags and check out the experimental version:

```bash
git fetch --tags
git checkout v0.19.0-experimental.1
```

Confirm the version checkout:

```bash
git describe --tags --exact-match
```

It should print:

```text
v0.19.0-experimental.1
```

Checking out a version tag creates a detached checkout. That is fine when installing and running PETEY. If you intend to edit the source, create a local branch:

```bash
git switch -c mbo-experimental
```

## 5. Create PETEY's Python environment

From the `PETEY-DESKTOP` directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

## 6. Start experimental PETEY

The `petey-mbo` Cloudflare tunnel must route `mbo.meetpetey.com` to `http://localhost:8765` on this computer.

Start PETEY with:

```bash
cd ~/PETEY-DESKTOP

.venv/bin/python run_desktop.py \
  --cloudflare \
  --cloudflare-hostname 'mbo.meetpetey.com' \
  --port 8765
```

PETEY will print a private mobile pairing link resembling:

```text
https://mbo.meetpetey.com/?access_token=LONG_PRIVATE_TOKEN
```

Open the complete link on the intended phone or tablet. Keep the token private.

## 7. Install PETEY in the Linux application menu

Run this once from the experimental checkout:

```bash
cd ~/PETEY-DESKTOP

.venv/bin/python run_desktop.py \
  --install-shortcut \
  --cloudflare \
  --cloudflare-hostname 'mbo.meetpetey.com' \
  --port 8765
```

The installer creates or updates the current user's PETEY application-menu entry and exits. Search the Linux application menu for **PETEY** and launch it.

The menu shortcut retains:

```text
--cloudflare --cloudflare-hostname mbo.meetpetey.com --port 8765
```

PETEY's Restart button also preserves those Cloudflare arguments.

## 8. Confirm the Cloudflare service

If `cloudflared` was installed as a system service, verify it with:

```bash
systemctl is-active cloudflared
```

The expected response is:

```text
active
```

For more detail:

```bash
sudo systemctl status cloudflared --no-pager
```

If the service needs to be restarted:

```bash
sudo systemctl restart cloudflared
```

## 9. Normal startup

After restarting the computer:

1. Confirm `cloudflared` is active.
2. Open **PETEY** from the Linux application menu.
3. Visit `https://mbo.meetpetey.com` from a previously paired browser.
4. If the browser is not paired, use the complete private link printed by PETEY.

## Troubleshooting

### GitHub says the repository was not found

Confirm authentication and repository access:

```bash
gh auth status
gh repo view bizzomephisto/PETEY-DESKTOP
```

The account must have access because PETEY Desktop is a private repository.

### Cloudflare shows Bad Gateway

Confirm PETEY is running on port `8765`:

```bash
ss -ltn | grep ':8765'
```

Confirm the Cloudflare published application uses:

```text
Hostname:    mbo.meetpetey.com
Service URL: http://localhost:8765
```

### PETEY says phone access requires the private link

Open the complete URL printed by PETEY, including `?access_token=...`. The bare hostname is intentionally blocked until the browser is paired.

### The menu shortcut starts the wrong PETEY checkout

Open a terminal in the intended checkout and run the `--install-shortcut` command again. PETEY records the Python executable and `run_desktop.py` path from the checkout used to install the shortcut.

## Related guide

The complete permanent Cloudflare Tunnel setup is in [`CLOUDFLARE_ACCOUNT_MOBILE_SETUP.md`](CLOUDFLARE_ACCOUNT_MOBILE_SETUP.md).
