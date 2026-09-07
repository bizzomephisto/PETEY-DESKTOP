# PETEY Wiki source

These files are the maintained source for PETEY's GitHub Wiki. GitHub stores the
published wiki in the separate `PETEY-DESKTOP.wiki.git` repository.

To publish after the wiki has been initialized:

```bash
git clone https://github.com/bizzomephisto/PETEY-DESKTOP.wiki.git /tmp/petey-wiki
cp docs/wiki/*.md /tmp/petey-wiki/
cd /tmp/petey-wiki
git add .
git commit -m "Build PETEY user guide"
git push origin master
```

Keep user-facing behavior aligned with the application and its in-app Help page.
