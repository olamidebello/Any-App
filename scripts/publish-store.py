#!/usr/bin/env python3
"""Register AnyApps in the inspected Africa Apps Store hosted_apps schema."""
import argparse,hashlib,json,shlex,sqlite3,subprocess,time,urllib.request,zipfile
from pathlib import Path
DOMAIN='anyapp.olamidepanel.com'

def database_from_service():
    env=subprocess.check_output(['systemctl','show','africanappsstore.service','--property=Environment','--value'],text=True)
    values=dict(part.split('=',1) for part in shlex.split(env) if '=' in part)
    return Path(values.get('STORE_DATA','/var/lib/africanappsstore'))/'store.sqlite3'

def install(database,apk,digest):
    if hashlib.sha256(apk.read_bytes()).hexdigest()!=digest: raise ValueError('Local APK checksum mismatch')
    with zipfile.ZipFile(apk) as z:
        if not {'classes.dex','AndroidManifest.xml'}.issubset(z.namelist()): raise ValueError('Not an Android package')
    if not database.is_file(): raise ValueError('Existing store database not found')
    metadata=dict(domain=DOMAIN,name='AnyApps',category='Developer tools',package='com.olamidepanel.anyapps.dev',version='1.0.0-dev',channel='development',website='https://'+DOMAIN,privacy='https://'+DOMAIN+'/legal/privacy',terms='https://'+DOMAIN+'/legal/terms',description='Describe, sketch and design your software idea. App creation package includes free static web hosting, a free Olamidepanel subdomain and store listing submission.',slogan='No idea is too small. Bring yours to life.',icon='https://'+DOMAIN+'/static/brand/icon.png',features=['Idea briefs and visual layout studio','Touch sketches, drag and drop blocks and color styling','Private project previews and source downloads','Admin-managed $999 default package and seven-day delivery target','Delivery change notifications in your dashboard'],limitations='Development Android website client. Internet and an operational AnyApps website required. This release generates static browser apps; complex backend work requires scope review. No offline generation or native push notifications.',apk_url='https://'+DOMAIN+'/download/android',sha256=digest,download_status='available')
    backup=database.with_name('store-before-anyapps-'+time.strftime('%Y%m%d-%H%M%S')+'.sqlite3')
    with sqlite3.connect(database,timeout=30) as c:
        columns={r[1] for r in c.execute('PRAGMA table_info(hosted_apps)')}
        if not {'domain','metadata','visible','updated'}.issubset(columns): raise ValueError('Store schema does not match the inspected source')
        with sqlite3.connect(backup) as dest: c.backup(dest)
        backup.chmod(0o600)
        c.execute('INSERT INTO hosted_apps(domain,metadata,updated) VALUES(?,?,?) ON CONFLICT(domain) DO UPDATE SET metadata=excluded.metadata,updated=excluded.updated',(DOMAIN,json.dumps(metadata),int(time.time())))
        visible=c.execute('SELECT visible FROM hosted_apps WHERE domain=?',(DOMAIN,)).fetchone()[0]
    return bool(visible)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--database',type=Path);p.add_argument('--apk',type=Path,default=Path('/var/lib/anyapps/downloads/AnyApps.apk'));a=p.parse_args()
    digest=hashlib.sha256(a.apk.read_bytes()).hexdigest()
    # Never advertise a broken download or a domain pointing at the wrong service.
    with urllib.request.urlopen('https://'+DOMAIN+'/health',timeout=20) as r:
        if json.load(r).get('service')!='AnyApps': raise SystemExit('Public AnyApps health check failed')
    with urllib.request.urlopen('https://'+DOMAIN+'/download/android',timeout=60) as r:
        if hashlib.sha256(r.read(10000001)).hexdigest()!=digest: raise SystemExit('Public APK differs from verified local APK')
    visible=install(a.database or database_from_service(),a.apk,digest)
    with urllib.request.urlopen('https://africanappsstore.space/api/hosted-apps',timeout=30) as r: catalog=json.load(r)
    if visible and not any(row.get('domain')==DOMAIN and row.get('sha256')==digest for row in catalog): raise SystemExit('Local catalog updated, but public store read-back has not confirmed it')
    print('AnyApps catalog updated and public read-back verified.' if visible else 'AnyApps catalog updated; existing hidden visibility was preserved.')
