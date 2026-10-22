#!/usr/bin/env python3
"""Reuse a specified existing key file; never display secrets or rewrite existing configuration."""
import argparse, os, secrets
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',default='');a=p.parse_args()
target=Path('/etc/anyapps/anyapps.env')
def read(path):
    values={}
    if not path.is_file() or path.is_symlink(): return values
    for line in path.read_text().splitlines():
        line=line.strip()
        if line.startswith('export '): line=line[7:]
        if '=' not in line or line.startswith('#'): continue
        key,value=line.split('=',1);values[key.strip()]=value.strip().strip('"\'')
    return values
old=read(target)
values={'SECRET_KEY':secrets.token_hex(32),'DATABASE':'/var/lib/anyapps/anyapps.sqlite3','PUBLIC_URL':'https://anyapp.olamidepanel.com','COOKIE_SECURE':'1','TRUST_PROXY':'1','PUBLISH_ROOT':'/srv/anyapps-sites','STORE_EXPORT_ROOT':'/var/lib/anyapps/store-feed'}
values.update(old)
allowed=('OPENAI_API_KEY','STRIPE_SECRET_KEY','STRIPE_WEBHOOK_SECRET','PAYSTACK_SECRET_KEY','FLUTTERWAVE_SECRET_KEY')
# Prefer the explicitly selected source; do not crawl unrelated applications for secrets.
source=read(Path(a.source)) if a.source else {}
for key in allowed:
    if not values.get(key):
        val=source.get(key) or os.environ.get(key)
        if val and '\n' not in val and '\r' not in val: values[key]=val
if not values.get('OPENAI_API_KEY'):
    print('No existing OPENAI_API_KEY found. Pass anyapps_existing_env_file pointing to its server environment file. App generation remains disabled until configured.')
if not target.exists() or any(values.get(k)!=old.get(k) for k in values):
    temp=target.with_suffix('.tmp');temp.write_text(''.join(k+'="'+v.replace('\\','\\\\').replace('"','\\"')+'"\n' for k,v in values.items()));temp.chmod(0o640);temp.replace(target)
print('Environment ready; values redacted.')
