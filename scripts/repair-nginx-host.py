#!/usr/bin/env python3
"""Detach only the AnyApps exact hostname from other active nginx vhosts."""
import argparse,json,re,shutil,subprocess,tempfile
from pathlib import Path
HOST='anyapp.olamidepanel.com'
TOKEN=re.compile(r'#[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{};]|[^\s{};#]+')

def detach_host(text,host=HOST):
    tokens=[m for m in TOKEN.finditer(text) if not m.group().startswith('#')]
    replacements=[]
    for i,token in enumerate(tokens):
        if token.group()!='server_name': continue
        values=[]
        for value in tokens[i+1:]:
            if value.group()==';': break
            if value.group() in ('{','}'): raise ValueError('Malformed server_name directive')
            values.append(value)
        target=[v for v in values if v.group().strip('"\'').lower()==host]
        remaining=[v for v in values if v not in target]
        for value in target:
            replacements.append((value.start(),value.end(),'' if remaining else 'detached-anyapp.olamidepanel.invalid'))
    for start,end,value in reversed(replacements): text=text[:start]+value+text[end:]
    return text,len(replacements)

def restore(manifest):
    state=json.loads(manifest.read_text())
    for entry in state:
        shutil.copy2(entry['backup'],entry['path'])
    print('Restored prior hostname mappings; nginx has not been reloaded.')

def apply(manifest):
    subprocess.run(['nginx','-t'],check=True,capture_output=True)
    own=Path('/etc/nginx/sites-available/anyapps').resolve()
    paths=set()
    for base,pattern in [('/etc/nginx/sites-enabled','*'),('/etc/nginx/conf.d','*.conf')]:
        paths.update(p.resolve() for p in Path(base).glob(pattern) if p.is_file())
    planned=[]
    for path in sorted(paths):
        if path==own:continue
        original=path.read_text();updated,count=detach_host(original)
        if count:planned.append((path,updated,count))
    backup=manifest.parent;backup.mkdir(parents=True,exist_ok=True);backup.chmod(0o700)
    state=[]
    for i,(path,updated,count) in enumerate(planned):
        dest=backup/('original-'+str(i)+'.conf');shutil.copy2(path,dest);state.append({'path':str(path),'backup':str(dest)})
    manifest.write_text(json.dumps(state));manifest.chmod(0o600)
    try:
        for path,updated,count in planned:path.write_text(updated)
    except Exception:
        restore(manifest);raise
    print(json.dumps({'changed':bool(planned),'detached_files':[str(p) for p,_,_ in planned]}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--restore',action='store_true');a=parser.parse_args()
    if a.restore:restore(a.manifest)
    else:apply(a.manifest)
