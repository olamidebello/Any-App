#!/usr/bin/env python3
"""Write a separate feed; never overwrite a store's existing catalog."""
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--store-root',required=True);a=p.parse_args()
root=Path(a.store_root).resolve()
if not root.is_dir(): raise SystemExit('Configured store root must already exist.')
feed={'schema_version':1,'apps':[{'id':'anyapps','name':'AnyApps','description':'No idea is too small. Bring yours to life. App creation, hosting and a free subdomain.','url':'https://anyapp.olamidepanel.com','download_url':'https://anyapp.olamidepanel.com/download/android','icon_url':'https://anyapp.olamidepanel.com/static/brand/icon.png','category':'Developer tools','release_channel':'development'}]}
target=root/'anyapps-import.json';temp=root/'anyapps-import.json.tmp';temp.write_text(json.dumps(feed,indent=2));temp.chmod(0o644);temp.replace(target)
print('AnyApps feed exported. Store import and public listing still need verification.')
