#!/usr/bin/env python3
"""Detach only the AnyApps exact hostname from other active nginx vhosts."""
import argparse,ipaddress,json,re,shutil,subprocess,tempfile
from pathlib import Path
HOST='anyapp.olamidepanel.com'
TOKEN=re.compile(r'#[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{};]|[^\s{};#]+')

def active_files(dump):
    return {Path(p).resolve() for p in re.findall(r'^# configuration file (.+):$',dump,re.M)}

def listen_addresses(dump,port):
    """Include existing explicit address groups, which take precedence over wildcard binds."""
    addresses={str(port)}
    tokens=[m.group() for m in TOKEN.finditer(dump) if not m.group().startswith('#')]
    for i,token in enumerate(tokens):
        if token!='listen':continue
        values=[]
        for value in tokens[i+1:]:
            if value in (';','{','}'):break
            values.append(value)
        if not values or 'proxy_protocol' in values:continue
        if port==443 and 'ssl' not in values:continue
        endpoint=values[0]
        match=re.fullmatch(r'(\[[0-9a-fA-F:]+\]|[0-9.]+):'+str(port),endpoint)
        if not match:continue
        host=match[1].strip('[]')
        try:ipaddress.ip_address(host)
        except ValueError:continue
        if host!='0.0.0.0':addresses.add(endpoint)
    return sorted(addresses,key=lambda a:(a!=str(port),a))

def discover():
    config=subprocess.run(['nginx','-T'],check=True,capture_output=True,text=True).stdout
    return {'http_listens':listen_addresses(config,80),'https_listens':listen_addresses(config,443),'active_files':sorted(str(p) for p in active_files(config))}

def diagnose():
    result=discover()
    try:
        handshake=subprocess.run(['openssl','s_client','-connect','127.0.0.1:443','-servername',HOST,'-showcerts'],input='',text=True,capture_output=True,timeout=10)
        cert=re.search(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',handshake.stdout,re.S)
        if cert:
            info=subprocess.run(['openssl','x509','-noout','-subject','-issuer','-ext','subjectAltName'],input=cert.group(),text=True,capture_output=True,timeout=5)
            result['served_certificate']=info.stdout.strip()
        else:result['served_certificate']='No TLS certificate received from loopback listener'
    except subprocess.TimeoutExpired:result['served_certificate']='TLS diagnostic timed out'
    return result

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
    config=subprocess.run(['nginx','-T'],check=True,capture_output=True,text=True).stdout
    own=Path('/etc/nginx/sites-available/anyapps').resolve()
    paths=active_files(config)
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
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path);parser.add_argument('--restore',action='store_true');parser.add_argument('--discover',action='store_true');parser.add_argument('--diagnose',action='store_true');a=parser.parse_args()
    if a.discover:print(json.dumps(discover()));raise SystemExit(0)
    if a.diagnose:print(json.dumps(diagnose()));raise SystemExit(0)
    if not a.manifest:parser.error('--manifest is required for mutations')
    if a.restore:restore(a.manifest)
    else:apply(a.manifest)
