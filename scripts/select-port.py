#!/usr/bin/env python3
"""Select a free loopback port without stopping other services."""
import argparse,json,socket,urllib.request
from pathlib import Path

def serves_anyapps(port):
    try:
        # Never use an outbound proxy for a local service identity check.
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:'+str(port)+'/health',timeout=1) as r:
            data=json.loads(r.read(4096))
            return data.get('service')=='AnyApps' and data.get('status')=='ok'
    except Exception:return False

def free(port):
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as listener:
        try:listener.bind(('127.0.0.1',port));return True
        except OSError:return False

def select(preferred,saved=None,start=18841,end=18940):
    candidates=list(dict.fromkeys(([saved] if saved else [])+[preferred]+list(range(start,end))))
    for port in candidates:
        if not isinstance(port,int) or not 1024<=port<=65535:continue
        if free(port) or serves_anyapps(port):return port
    raise RuntimeError('No available AnyApps port in the configured range; existing services were left running.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--preferred',type=int,default=18840);p.add_argument('--state',type=Path,default=Path('/var/lib/anyapps/listen-port.json'));a=p.parse_args()
    old={}
    if a.state.exists():
        try:old=json.loads(a.state.read_text())
        except (ValueError,OSError):pass
    port=select(a.preferred,old.get('port'))
    changed=old.get('port')!=port
    if changed:
        a.state.parent.mkdir(parents=True,exist_ok=True)
        temp=a.state.with_suffix('.tmp');temp.write_text(json.dumps({'port':port}));temp.chmod(0o644);temp.replace(a.state)
    print(json.dumps({'port':port,'changed':changed}))
