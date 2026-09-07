# Updating PETEY

Close PETEY and open a terminal in its project folder. If you have local source
changes, commit or stash them first.

## Update the code and dependencies

Linux and macOS:

```bash
source .venv/bin/activate
git pull --ff-only
python -m pip install -r requirements.txt
python run_desktop.py
```

Windows:

```powershell
.venv\Scripts\activate
git pull --ff-only
python -m pip install -r requirements.txt
python run_desktop.py
```

`--ff-only` stops instead of overwriting or merging divergent local work.

## Refresh the Linux launcher

Run this after moving PETEY or replacing its environment:

```bash
python run_desktop.py --install-shortcut
```

The application-menu entry stores absolute paths. If PETEY does not open after a
move, this is usually the fix.

## Verify a development checkout

```bash
python -m unittest discover -s tests -v
node --check web/static/desktop.js
```

The Node syntax check is optional when Node.js is unavailable.
