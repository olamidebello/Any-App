"""Encrypted, write-only API credential management with environment fallback."""
import os,secrets,tempfile
from pathlib import Path
from cryptography.fernet import Fernet,InvalidToken

CREDENTIALS={
 'OPENAI_API_KEY':{'label':'OpenAI · App generation','prefixes':('sk-',),'help':'Server-side API key used by the build worker.'},
 'STRIPE_SECRET_KEY':{'label':'Stripe · Checkout','prefixes':('sk_test_','sk_live_','rk_test_','rk_live_'),'help':'Use a test key before switching to live payments.'},
 'STRIPE_WEBHOOK_SECRET':{'label':'Stripe · Webhook signing','prefixes':('whsec_',),'help':'Signing secret for /payments/stripe/webhook. Verification is tested locally.'},
 'PAYSTACK_SECRET_KEY':{'label':'Paystack · Checkout','prefixes':('sk_test_','sk_live_'),'help':'Merchant secret key; your account must support the checkout currency.'},
 'FLUTTERWAVE_SECRET_KEY':{'label':'Flutterwave · Checkout','prefixes':('FLWSECK',),'help':'Merchant secret key for hosted checkout and payment verification.'},
}
class VaultError(Exception):pass

def cipher(db):
    database=db.execute('PRAGMA database_list').fetchone()[2]
    key_path=Path(os.environ.get('ANYAPPS_VAULT_KEY_PATH',str(Path(database).parent/'api-vault.key')))
    if not key_path.exists():
        if db.execute('SELECT 1 FROM api_credentials WHERE ciphertext IS NOT NULL LIMIT 1').fetchone():raise VaultError('Encryption key is missing; restore its backup.')
        key_path.parent.mkdir(parents=True,exist_ok=True)
        fd,tmp=tempfile.mkstemp(prefix='.vault-',dir=key_path.parent)
        try:
            with os.fdopen(fd,'wb') as f:f.write(Fernet.generate_key());f.flush();os.fsync(f.fileno())
            try:os.link(tmp,key_path)
            except FileExistsError:pass
        finally:os.unlink(tmp)
    if key_path.is_symlink():raise VaultError('Encryption key must be a regular protected file.')
    try:return Fernet(key_path.read_bytes())
    except (ValueError,OSError) as e:raise VaultError('Encryption key is unavailable.') from e

def get(db,name):
    if name not in CREDENTIALS:raise ValueError('Unsupported credential')
    row=db.execute('SELECT ciphertext,enabled FROM api_credentials WHERE name=?',(name,)).fetchone()
    if row:
        if not row['enabled']:return None
        if row['ciphertext']:
            try:return cipher(db).decrypt(row['ciphertext'].encode()).decode()
            except InvalidToken as e:raise VaultError('Stored credential cannot be decrypted.') from e
    return os.environ.get(name) or None

def save(db,name,value,actor):
    if name not in CREDENTIALS:raise ValueError('Unsupported credential')
    if not 16<=len(value)<=4096 or any(ord(c)<33 or ord(c)>126 for c in value) or not value.startswith(CREDENTIALS[name]['prefixes']):raise ValueError('Key format does not match this provider.')
    encrypted=cipher(db).encrypt(value.encode()).decode()
    db.execute('INSERT INTO api_credentials(name,ciphertext,enabled,updated_by) VALUES(?,?,1,?) ON CONFLICT(name) DO UPDATE SET ciphertext=excluded.ciphertext,enabled=1,updated_by=excluded.updated_by,updated=CURRENT_TIMESTAMP,last_test=NULL,tested=NULL',(name,encrypted,actor))

def control(db,name,action,actor):
    if name not in CREDENTIALS:raise ValueError('Unsupported credential')
    if action not in ('enable','disable','remove'):raise ValueError('Unsupported action')
    row=db.execute('SELECT ciphertext FROM api_credentials WHERE name=?',(name,)).fetchone()
    ciphertext=row['ciphertext'] if row and action!='remove' else None
    db.execute('INSERT INTO api_credentials(name,ciphertext,enabled,updated_by) VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET ciphertext=excluded.ciphertext,enabled=excluded.enabled,updated_by=excluded.updated_by,updated=CURRENT_TIMESTAMP,last_test=NULL,tested=NULL',(name,ciphertext,int(action=='enable'),actor))

def statuses(db):
    out=[]
    for name,definition in CREDENTIALS.items():
        row=db.execute('SELECT * FROM api_credentials WHERE name=?',(name,)).fetchone()
        enabled=not row or bool(row['enabled']);stored=bool(row and row['ciphertext'])
        try:configured=bool(get(db,name));error=False
        except VaultError:configured=False;error=True
        out.append(dict(name=name,**{k:v for k,v in definition.items() if k!='prefixes'},enabled=enabled,configured=configured,source='Encrypted vault' if stored else 'Server environment' if os.environ.get(name) else 'Not configured',error=error,last_test=row['last_test'] if row else None,tested=row['tested'] if row else None))
    return out
