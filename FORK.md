# Fork notes

This is a fork of [RookieEnough/Morphe-AutoBuilds](https://github.com/RookieEnough/Morphe-AutoBuilds).
Everything here is fork-only: these files do not exist upstream, so upstream syncs
never conflict with them.

## Why the fork used to break on sync

The fork edited `patch-config.json` to build only a subset of the apps. Upstream edits
that same file constantly, so every *Sync fork* attempt hit a conflict and the fork
silently drifted behind.

## How it works now

Upstream owns `patch-config.json` outright. The fork's app selection lives in
`fork-config.json`, and `scripts/apply_fork_config.py` rebuilds `patch-config.json`
from upstream's copy filtered by that list:

```bash
python3 scripts/apply_fork_config.py           # rewrite patch-config.json
python3 scripts/apply_fork_config.py --check   # exit 1 if it needs rewriting
```

Because the selection is derived from upstream rather than frozen, upstream changes to
an app you build (a new `source`, for example) are inherited automatically. Apps you do
not build are simply dropped.

To add or remove an app, edit `apps` in `fork-config.json` and run the script.
`source_overrides` pins a source different from upstream's for a given app.

## Automatic sync

`.github/workflows/sync-upstream.yml` runs daily at 04:00 UTC (and on demand via
*Actions -> Sync Upstream -> Run workflow*). It merges `upstream/main`, resolves
`patch-config.json` in upstream's favour, re-applies the fork selection and pushes.
Any other conflict fails the job instead of guessing.

### Required secret: `SYNC_PAT`

The default `GITHUB_TOKEN` **cannot push changes under `.github/workflows/`**, and
upstream touches those files regularly. Create a token and add it as the repository
secret `SYNC_PAT`:

- Classic PAT: scopes `repo` + `workflow`.
- Fine-grained PAT on this repository: Contents *read and write* + Workflows *read and write*.

Without the secret the workflow still runs, but it fails with an explicit error whenever
a sync would change a workflow file.
