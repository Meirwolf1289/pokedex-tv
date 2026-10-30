#!/usr/bin/env python3
"""Builds Hush for Samsung TVs: Pokedex-tizen.wgt, the package the TV installs.

    python3 tizen/build.py                 # -> Pokedex-tizen.wgt, unsigned: TizenBrew Installer signs it on the TV (2023+)
    python3 tizen/build.py --sign PROFILE  # signed with `tizen package` (Tizen Studio) for tizen/install.py

A .wgt is a zip of the web app plus config.xml and icon.png. Python 3 only.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WGT = os.path.join(ROOT, 'Pokedex-tizen.wgt')
FILES = ['index.html']


def tizen_cli():
    name = 'tizen.bat' if os.name == 'nt' else 'tizen'
    for base in (os.environ.get('TIZEN_STUDIO', ''), os.path.expanduser('~/tizen-studio'), 'C:\\tizen-studio'):
        path = os.path.join(base, 'tools', 'ide', 'bin', name)
        if base and os.path.exists(path):
            return path
    return shutil.which('tizen')


def sign(profile):
    cli = tizen_cli()
    if not cli:
        sys.exit('Signing needs Tizen Studio. Set TIZEN_STUDIO to where it is installed, or install through TizenBrew instead.')
    out = tempfile.mkdtemp()
    try:
        run = subprocess.run([cli, 'package', '-t', 'wgt', '-s', profile, '-o', out, '--', WGT], capture_output=True, text=True)
        made = [n for n in os.listdir(out) if n.endswith('.wgt')]
        if run.returncode != 0 or not made:
            sys.exit('`tizen package` did not sign it:\n' + (run.stdout + run.stderr).strip())
        shutil.move(os.path.join(out, made[0]), WGT)
    finally:
        shutil.rmtree(out, ignore_errors=True)


def page():
    """index.html with config.local.json (TMDB key, region) baked in; the file is git-ignored and never shown."""
    with open(os.path.join(ROOT, 'index.html'), encoding='utf-8') as f:
        html = f.read()
    cfg = os.path.join(ROOT, 'config.local.json')
    if os.path.exists(cfg):
        import json
        with open(cfg, encoding='utf-8') as f:
            conf = json.load(f)
        html = html.replace('window.HUSH_CONFIG = {};', 'window.HUSH_CONFIG = ' + json.dumps({'tmdbKey': conf.get('tmdb_key', ''), 'region': conf.get('region', 'IL')}) + ';', 1)
        print('With the TMDB key from config.local.json.')
    return html.encode('utf-8')


def build(profile):
    with zipfile.ZipFile(WGT, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in FILES:
            if name == 'index.html':
                z.writestr(name, page())
            else:
                z.write(os.path.join(ROOT, name), name)
        for name in ('config.xml', 'icon.png'):
            z.write(os.path.join(ROOT, 'tizen', name), name)
    if profile:
        sign(profile)
    print('Built %s (%d KB)%s' % (os.path.basename(WGT), os.path.getsize(WGT) // 1024, '' if profile else ', unsigned'))


if __name__ == '__main__':
    args = sys.argv[1:]
    build(args[args.index('--sign') + 1] if '--sign' in args else None)
