#!/usr/bin/env python3
"""Builds Hush for LG TVs: Pokedex-webos.ipk, the package the TV's Developer Mode installs.

    python3 webos/build.py   # -> Pokedex-webos.ipk

Packs the web app and webos/appinfo.json the way LG's ares-package does (an ar archive holding control.tar.gz and
data.tar.gz), so no LG tools are needed. Packer after Free My TV (MIT). Python 3 only.
"""
import io
import json
import os
import tarfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IPK = os.path.join(ROOT, 'Pokedex-webos.ipk')
FILES = ['index.html']


def tar_gz(entries):
    """A .tar.gz from [(name, bytes or None for a directory)], owned by root."""
    buf = io.BytesIO()
    now = int(time.time())
    with tarfile.open(fileobj=buf, mode='w:gz', format=tarfile.PAX_FORMAT) as tar:
        for name, data in entries:
            info = tarfile.TarInfo(name)
            info.mtime = now
            info.uid = info.gid = 0
            if data is None:
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                tar.addfile(info)
            else:
                info.size = len(data)
                info.mode = 0o644
                tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def ar(members):
    out = io.BytesIO()
    out.write(b'!<arch>\n')
    now = int(time.time())
    for name, data in members:
        out.write(('%-16s%-12d%-6d%-6d%-8s%-10d`\n' % (name, now, 0, 0, '100644', len(data))).encode('ascii'))
        out.write(data)
        if len(data) % 2:
            out.write(b'\n')
    return out.getvalue()


def build():
    with open(os.path.join(ROOT, 'webos', 'appinfo.json'), encoding='utf-8') as f:
        info = json.load(f)
    app_id, version = info['id'], info['version']
    import sys
    sys.path.insert(0, os.path.join(ROOT, 'tizen'))
    from build import page  # the same config.local.json baking as the Samsung package
    app = {'index.html': page()}
    for name in ('appinfo.json', 'icon.png', 'largeIcon.png'):
        with open(os.path.join(ROOT, 'webos', name), 'rb') as f:
            app[name] = f.read()

    base = 'usr/palm/applications/' + app_id
    entries = [('usr', None), ('usr/palm', None), ('usr/palm/applications', None), (base, None)]
    entries += [(base + '/' + path, app[path]) for path in sorted(app)]
    package = json.dumps({'id': app_id, 'version': version, 'app': app_id}, indent=2).encode('utf-8')
    entries += [('usr/palm/packages', None), ('usr/palm/packages/' + app_id, None),
                ('usr/palm/packages/' + app_id + '/packageinfo.json', package)]

    size = sum(len(d) for d in app.values()) + len(package)
    control = ('Package: %s\nVersion: %s\nSection: misc\nPriority: optional\nArchitecture: all\nInstalled-Size: %d\n'
               'Maintainer: Hush\nDescription: A home screen with nothing on it.\n'
               'webOS-Package-Format-Version: 2\nwebOS-Packager-Version: 1.0.0\n' % (app_id, version, size))
    data = ar([('debian-binary', b'2.0\n'), ('control.tar.gz', tar_gz([('control', control.encode('utf-8'))])),
               ('data.tar.gz', tar_gz(entries))])
    with open(IPK, 'wb') as f:
        f.write(data)
    print('Built %s (%s %s, %d KB)' % (os.path.basename(IPK), app_id, version, len(data) // 1024))


if __name__ == '__main__':
    build()
