#!/usr/bin/env python3
"""Install the CI APK only after verifying the accompanying SHA-256 digest."""
import hashlib,json,tempfile,urllib.request
from pathlib import Path
api='https://api.github.com/repos/olamidebello/Any-App/releases/tags/android-development'
try:
    with urllib.request.urlopen(api,timeout=30) as r: release=json.load(r)
    assets={x['name']:x['browser_download_url'] for x in release['assets']}
    def fetch(name):
        with urllib.request.urlopen(assets[name],timeout=120) as r: return r.read()
    apk=fetch('AnyApps.apk');expected=fetch('AnyApps.apk.sha256').decode().split()[0]
    if hashlib.sha256(apk).hexdigest()!=expected: raise ValueError('APK checksum mismatch')
    target=Path('/var/lib/anyapps/downloads');target.mkdir(parents=True,exist_ok=True)
    temp=target/'AnyApps.apk.tmp';temp.write_bytes(apk);temp.chmod(0o644);temp.replace(target/'AnyApps.apk')
    print('Android development APK installed with verified checksum. Not a Play Store production release.')
except Exception as e:
    raise SystemExit('Android release unavailable or verification failed: '+type(e).__name__)
