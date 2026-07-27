#!/usr/bin/env python3
"""Publish one GitHub release per app so Obtainium can track versions.

Fork-only script. The upstream build publishes every APK into a single reusable
release tagged 'latest', which Obtainium cannot use for version detection: the
tag never changes, so no update is ever detected, and using the release title as
a version reports a fake update on every daily build.

This mirrors each app's APKs into its own release tagged '{app}-v{version}', which
Obtainium tracks exactly. The 'latest' release is left untouched.

Usage:
    python3 scripts/publish_app_releases.py [--dry-run] [--keep N] [--source-release latest]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATCH_CONFIG = os.path.join(REPO_ROOT, 'patch-config.json')

ARCHES = ['universal', 'arm64-v8a', 'armeabi-v7a', 'x86_64', 'x86']
ASSET_RE = re.compile(
    r'^(?P<app>.+?)-(?P<arch>' + '|'.join(ARCHES) + r')-'
    r'(?P<source>.+)-v(?P<version>[0-9][^-]*)\.apk$'
)


def repo_slug():
    """Resolve owner/repo explicitly: this checkout has an 'upstream' remote too,
    and gh refuses to guess (or guesses wrong) when several remotes exist."""
    env = os.environ.get('GITHUB_REPOSITORY')
    if env:
        return env
    url = subprocess.check_output(['git', 'remote', 'get-url', 'origin'],
                                  cwd=REPO_ROOT, text=True).strip()
    match = re.search(r'[:/]([^/:]+/[^/]+?)(?:\.git)?$', url)
    if not match:
        raise SystemExit(f'cannot derive owner/repo from origin url: {url}')
    return match.group(1)


REPO = repo_slug()


def gh(*args, check=True, capture=True):
    return subprocess.run(['gh', *args, '-R', REPO], cwd=REPO_ROOT, check=check,
                          text=True, capture_output=capture)


def active_apps():
    with open(PATCH_CONFIG, 'r') as f:
        return {entry['app_name'] for entry in json.load(f).get('patch_list', [])}


def version_key(version):
    """Sortable key for dotted versions like 7.79.0.924379438, digits-first."""
    return tuple(int(p) if p.isdigit() else -1 for p in version.split('.'))


def group_assets(assets, apps):
    """Group release assets by app, keeping only the most recently uploaded version."""
    by_app = {}
    for asset in assets:
        match = ASSET_RE.match(asset['name'])
        if not match:
            continue
        app = match.group('app')
        if app not in apps:
            continue
        version = match.group('version')
        entry = by_app.setdefault(app, {})
        bucket = entry.setdefault(version, [])
        bucket.append(asset)

    result = {}
    for app, versions in by_app.items():
        # A failed cleanup can leave several versions behind; the highest version
        # wins, with upload time only as a tie-breaker.
        newest = max(versions.items(),
                     key=lambda kv: (version_key(kv[0]), max(a['createdAt'] for a in kv[1])))
        result[app] = {'version': newest[0], 'assets': newest[1]}
    return result


def release_exists(tag):
    return gh('release', 'view', tag, check=False).returncode == 0


def publish(app, version, assets, source_release, dry_run):
    tag = f'{app}-v{version}'
    if release_exists(tag):
        print(f'  {tag}: already published, skipping')
        return False

    names = [a['name'] for a in assets]
    print(f'  {tag}: publishing {len(names)} asset(s): {", ".join(names)}')
    if dry_run:
        return True

    with tempfile.TemporaryDirectory() as tmp:
        for name in names:
            gh('release', 'download', source_release, '--pattern', name, '--dir', tmp)
        files = [os.path.join(tmp, name) for name in names]
        notes = (f'Automated build of **{app}** version `{version}`.\n\n'
                 f'Mirrored from the [`{source_release}`]'
                 f'(../../releases/tag/{source_release}) release so that Obtainium '
                 f'can track versions per app.')
        gh('release', 'create', tag, '--title', f'{app} {version}', '--notes', notes, *files)
    return True


def prune(app, keep, dry_run):
    """Keep only the newest `keep` releases for an app."""
    out = gh('release', 'list', '--limit', '200', '--json', 'tagName,createdAt').stdout
    tags = [r for r in json.loads(out) if r['tagName'].startswith(f'{app}-v')]
    tags.sort(key=lambda r: r['createdAt'], reverse=True)
    for stale in tags[keep:]:
        print(f'  {stale["tagName"]}: pruning (keeping newest {keep})')
        if not dry_run:
            gh('release', 'delete', stale['tagName'], '--yes', '--cleanup-tag', check=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--keep', type=int, default=3,
                        help='per-app releases to retain (default: 3)')
    parser.add_argument('--source-release', default='latest')
    args = parser.parse_args()

    apps = active_apps()
    print(f'Active apps: {", ".join(sorted(apps))}')

    out = gh('release', 'view', args.source_release, '--json', 'assets').stdout
    assets = json.loads(out).get('assets', [])
    grouped = group_assets(assets, apps)

    if not grouped:
        print(f'No matching APK assets in the {args.source_release} release')
        return 0

    published = 0
    for app in sorted(grouped):
        info = grouped[app]
        if publish(app, info['version'], info['assets'], args.source_release, args.dry_run):
            published += 1
        prune(app, args.keep, args.dry_run)

    missing = sorted(apps - set(grouped))
    if missing:
        print(f'WARNING: no APK found for: {", ".join(missing)}')

    print(f'Published {published} new app release(s)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
