#!/usr/bin/env python3
"""Regenerate patch-config.json from upstream's version + this fork's app selection.

Upstream owns patch-config.json entirely. This fork only owns fork-config.json,
which lists the apps it actually builds. Keeping the selection in a fork-only file
means upstream syncs never conflict: patch-config.json is taken verbatim from
upstream and filtered afterwards by this script.

Usage:
    python3 scripts/apply_fork_config.py            # rewrite patch-config.json
    python3 scripts/apply_fork_config.py --check    # exit 1 if it needs rewriting
"""
import json
import os
import subprocess
import sys
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORK_CONFIG = os.path.join(REPO_ROOT, 'fork-config.json')
PATCH_CONFIG = os.path.join(REPO_ROOT, 'patch-config.json')

UPSTREAM_REF = 'upstream/main'
UPSTREAM_RAW = 'https://raw.githubusercontent.com/RookieEnough/Morphe-AutoBuilds/main/patch-config.json'


def load_upstream_catalog():
    """Fetch upstream's full patch_list: the local file is already filtered down.

    Tries the fetched upstream remote first so it works offline, then the raw URL.
    Returns None if neither is reachable.
    """
    try:
        raw = subprocess.check_output(
            ['git', 'show', f'{UPSTREAM_REF}:patch-config.json'],
            cwd=REPO_ROOT, stderr=subprocess.DEVNULL, text=True)
        return json.loads(raw).get('patch_list', [])
    except (subprocess.CalledProcessError, OSError, ValueError):
        pass

    try:
        with urllib.request.urlopen(UPSTREAM_RAW, timeout=20) as resp:
            return json.loads(resp.read().decode()).get('patch_list', [])
    except Exception as exc:  # noqa: BLE001 - any failure means "no catalog"
        print(f'WARNING: could not read upstream patch-config.json ({exc})')
        return None


def build_patch_list(patch_list, selected, overrides):
    """Filter upstream's patch_list down to the fork's apps, keeping upstream order."""
    wanted = set(selected)
    seen = set()
    result = []

    for entry in patch_list:
        app_name = entry.get('app_name')
        if app_name not in wanted or app_name in seen:
            continue
        seen.add(app_name)
        result.append({
            'app_name': app_name,
            'source': overrides.get(app_name, entry.get('source')),
        })

    # Apps we want that upstream no longer ships: keep them only if the fork
    # pins a source itself, otherwise there is nothing to build them from.
    for app_name in selected:
        if app_name in seen:
            continue
        if app_name in overrides:
            seen.add(app_name)
            result.append({'app_name': app_name, 'source': overrides[app_name]})
        else:
            print(f"WARNING: '{app_name}' is in fork-config.json but not in upstream's "
                  f"patch-config.json and has no source_overrides entry; skipping it")

    return result


def render(patch_list):
    """Render patch-config.json one app per line, matching upstream's formatting."""
    lines = ['{', '  "patch_list": [']
    for i, entry in enumerate(patch_list):
        comma = ',' if i < len(patch_list) - 1 else ''
        lines.append(f'    {{ "app_name": "{entry["app_name"]}", "source": "{entry["source"]}" }}{comma}')
    lines.append('  ]')
    lines.append('}')
    return '\n'.join(lines) + '\n'


def main():
    check_only = '--check' in sys.argv

    with open(FORK_CONFIG, 'r') as f:
        fork_config = json.load(f)
    with open(PATCH_CONFIG, 'r') as f:
        patch_config = json.load(f)

    selected = fork_config.get('apps') or []
    if not selected:
        print("ERROR: fork-config.json has an empty 'apps' list; refusing to wipe patch-config.json")
        return 1

    # Upstream owns the catalog; fall back to the local (already filtered) file
    # only when upstream is unreachable, in which case new apps cannot be resolved.
    catalog = load_upstream_catalog()
    if catalog is None:
        print('WARNING: falling back to the local patch-config.json as catalog')
        catalog = patch_config.get('patch_list', [])

    patch_list = build_patch_list(
        catalog,
        selected,
        fork_config.get('source_overrides') or {},
    )
    if not patch_list:
        print('ERROR: filtering produced an empty patch_list; refusing to write')
        return 1

    new_content = render(patch_list)
    with open(PATCH_CONFIG, 'r') as f:
        current = f.read()

    if new_content == current:
        print(f'patch-config.json already matches fork selection ({len(patch_list)} apps)')
        return 0

    if check_only:
        print('patch-config.json is out of sync with fork-config.json; run scripts/apply_fork_config.py')
        return 1

    with open(PATCH_CONFIG, 'w') as f:
        f.write(new_content)
    print(f'Wrote patch-config.json with {len(patch_list)} apps')
    return 0


if __name__ == '__main__':
    sys.exit(main())
