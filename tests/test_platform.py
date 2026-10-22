import hashlib,hmac,json,time
import pytest
from werkzeug.security import generate_password_hash
from app import create_app

@pytest.fixture
def app(tmp_path,monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    app=create_app({'TESTING':True,'SECRET_KEY':'tests-only','DATABASE':str(tmp_path/'app.sqlite3'),'SESSION_COOKIE_SECURE':False})
    with app.app_context():
        for email,role in [('user@example.com','user'),('other@example.com','user'),('admin@example.com','admin')]:
            app.db().execute('INSERT INTO users(email,password,name,role,balance) VALUES(?,?,?,?,5)',(email,generate_password_hash('a-long-password-123'),'Creator',role))
    return app

@pytest.fixture
def client(app):
    c=app.test_client()
    with c.session_transaction() as s:s['uid']=1;s['csrf']='test-csrf'
    return c

def post(client,path,**data): return client.post(path,data={'csrf':'test-csrf',**data})
def project(client):
    r=post(client,'/projects',name='Community garden',idea='A shared garden planning app for local neighbors.',slug='garden-test',style='modern')
    return r.location.rsplit('/',1)[1]

def test_public_pages_and_admin_render(app,client):
    for path in ['/','/marketplace','/download','/legal/terms','/legal/privacy','/legal/copyright','/health','/dashboard']:
        assert client.get(path).status_code==200,path
    with client.session_transaction() as s:s['uid']=3
    assert client.get('/admin').status_code==200

def test_price_and_csrf(app,client):
    with app.app_context():
        p=app.db().execute('SELECT * FROM plans WHERE active=1').fetchall()
        assert len(p)==1 and p[0]['price']==99900
    assert client.post('/projects',data={'name':'oops'}).status_code==400
    assert client.get('/admin').status_code==403

def test_project_is_private_and_design_validated(app,client):
    pid=project(client)
    assert client.get('/projects/'+pid).status_code==200
    layout=json.dumps([{'type':'heading','text':'Hello','x':10,'y':20,'width':200,'height':60}])
    assert post(client,'/projects/'+pid+'/design',layout=layout,background='#ffffff',accent='#7047eb').status_code==302
    assert post(client,'/projects/'+pid+'/design',layout='[{"type":"script"}]').status_code==400
    with client.session_transaction() as s:s['uid']=2
    assert client.get('/projects/'+pid).status_code==404
    assert post(client,'/projects/'+pid+'/build').status_code==404

def test_missing_key_does_not_charge(app,client):
    pid=project(client);post(client,'/projects/'+pid+'/build')
    with app.app_context():
        assert app.db().execute('SELECT balance FROM users WHERE id=1').fetchone()[0]==5
        assert app.db().execute('SELECT COUNT(*) FROM builds').fetchone()[0]==0

def test_duplicate_build_and_failure_refund(app,client,monkeypatch):
    import worker
    monkeypatch.setenv('OPENAI_API_KEY','test-do-not-use')
    monkeypatch.setattr(worker,'api',lambda *args,**kw:(_ for _ in ()).throw(RuntimeError('unavailable')))
    pid=project(client);post(client,'/projects/'+pid+'/build');post(client,'/projects/'+pid+'/build')
    with app.app_context():
        assert app.db().execute('SELECT COUNT(*) FROM builds').fetchone()[0]==1
        assert app.db().execute('SELECT balance FROM users WHERE id=1').fetchone()[0]==4
        assert worker.process_build(app)
        assert app.db().execute('SELECT balance FROM users WHERE id=1').fetchone()[0]==5
        assert not worker.process_build(app)

def test_generation_receives_layout_and_preview_is_isolated(app,client,monkeypatch):
    import worker
    monkeypatch.setenv('OPENAI_API_KEY','test-do-not-use')
    def response(url,key,data):
        assert 'garden' in data['input'][0]['content'][0]['text']
        return {'status':'completed','output':[{'content':[{'type':'output_text','text':'<!doctype html><html><body>Hello<script>console.log(1)</script></body></html>'}]}]}
    monkeypatch.setattr(worker,'api',response)
    pid=project(client);post(client,'/projects/'+pid+'/build')
    with app.app_context():
        worker.process_build(app);bid=app.db().execute('SELECT id FROM builds').fetchone()[0]
    r=client.get('/builds/'+bid+'/preview');assert r.status_code==200
    assert "sandbox allow-scripts" in r.headers['Content-Security-Policy']
    assert "connect-src 'none'" in r.headers['Content-Security-Policy']
    assert client.get('/builds/'+bid+'/download').status_code==200
    with client.session_transaction() as s:s['uid']=2
    assert client.get('/builds/'+bid+'/preview').status_code==404

def test_webhook_idempotency_and_delivery(app,client,monkeypatch):
    monkeypatch.setenv('STRIPE_WEBHOOK_SECRET','whsec_test')
    pid=project(client)
    with app.app_context():
        app.db().execute("INSERT INTO orders(id,user_id,plan_id,amount,credits,provider,provider_ref) VALUES('order1',1,1,99900,5,'stripe','cs_test')")
        app.db().execute('INSERT INTO order_projects VALUES(?,?,?)',('order1',pid,7))
    def call(amount=99900,signature=True):
        event={'id':'evt_test','type':'checkout.session.completed','data':{'object':{'client_reference_id':'order1','id':'cs_test','amount_total':amount,'currency':'usd','payment_status':'paid'}}}
        body=json.dumps(event).encode();ts=str(int(time.time()));digest=hmac.new(b'whsec_test',ts.encode()+b'.'+body,hashlib.sha256).hexdigest()
        return client.post('/payments/stripe/webhook',data=body,headers={'Content-Type':'application/json','Stripe-Signature':f't={ts},v1={digest}' if signature else 'bad'})
    assert call(signature=False).status_code==400
    assert call(amount=1).status_code==400
    assert call().status_code==200;assert call().status_code==200
    with app.app_context():
        assert app.db().execute('SELECT balance FROM users WHERE id=1').fetchone()[0]==10
        assert app.db().execute('SELECT COUNT(*) FROM deliveries').fetchone()[0]==1
        assert app.db().execute('SELECT COUNT(*) FROM notifications').fetchone()[0]==1

def test_admin_changes_notify_and_prices_persist(app,client):
    pid=project(client)
    with client.session_transaction() as s:s['uid']=3
    r=post(client,'/admin/deliveries/'+pid,due='2027-01-01',status='delayed',note='Additional accessibility review is needed.')
    assert r.status_code==302
    post(client,'/admin/plans',id='1',name='AnyApps Complete',description='A complete app package',price='109900',credits='5',active='on')
    with app.app_context():
        assert 'accessibility' in app.db().execute('SELECT message FROM notifications').fetchone()[0]
        assert app.db().execute('SELECT price FROM plans WHERE id=1').fetchone()[0]==109900
    # Reinitialization must never reset the admin-managed price.
    create_app(app.config)
    with app.app_context():assert app.db().execute('SELECT price FROM plans WHERE id=1').fetchone()[0]==109900

def test_reserved_subdomain(app,client):
    post(client,'/projects',name='test',idea='This is a long enough description',slug='anyapp')
    with app.app_context():assert app.db().execute('SELECT COUNT(*) FROM projects').fetchone()[0]==0

def test_store_publisher_preserves_other_apps_and_visibility(tmp_path):
    import importlib.util,sqlite3,zipfile
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('publisher',Path(__file__).parents[1]/'scripts/publish-store.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    database=tmp_path/'store.sqlite3';apk=tmp_path/'app.apk'
    with zipfile.ZipFile(apk,'w') as z:z.writestr('classes.dex',b'test');z.writestr('AndroidManifest.xml',b'test')
    with sqlite3.connect(database) as c:
        c.execute('CREATE TABLE hosted_apps(domain TEXT PRIMARY KEY,metadata TEXT,visible INTEGER DEFAULT 1,updated INTEGER)')
        c.execute('INSERT INTO hosted_apps VALUES(?,?,?,?)',('existing.example','{}',1,1))
        c.execute('INSERT INTO hosted_apps VALUES(?,?,?,?)',(mod.DOMAIN,'{}',0,1))
    digest=hashlib.sha256(apk.read_bytes()).hexdigest()
    assert mod.install(database,apk,digest) is False
    with sqlite3.connect(database) as c:
        assert c.execute('SELECT COUNT(*) FROM hosted_apps').fetchone()[0]==2
        assert c.execute('SELECT metadata FROM hosted_apps WHERE domain=?',('existing.example',)).fetchone()[0]=='{}'
        assert json.loads(c.execute('SELECT metadata FROM hosted_apps WHERE domain=?',(mod.DOMAIN,)).fetchone()[0])['sha256']==digest

def test_hostname_repair_preserves_other_domains_and_comments():
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('nginx_repair',Path(__file__).parents[1]/'scripts/repair-nginx-host.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    text='''# server_name anyapp.olamidepanel.com;
server { listen 443 ssl; server_name afribulkhub.com anyapp.olamidepanel.com www.afribulkhub.com; proxy_pass http://127.0.0.1:8091; }
server { server_name "ANYAPP.OLAMIDEPANEL.COM"; }
server { server_name *.olamidepanel.com; }
'''
    result,count=mod.detach_host(text)
    assert count==2
    assert '# server_name anyapp.olamidepanel.com;' in result
    assert 'afribulkhub.com  www.afribulkhub.com' in result
    assert 'proxy_pass http://127.0.0.1:8091;' in result
    assert 'server_name detached-anyapp.olamidepanel.invalid;' in result
    assert 'server_name *.olamidepanel.com;' in result
    assert mod.detach_host(result)[1]==0

def test_port_selection_keeps_unrelated_service_running():
    import importlib.util,threading,urllib.request
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('port_selector',Path(__file__).parents[1]/'scripts/select-port.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200);self.end_headers();self.wfile.write(b'{"service":"africa-credit","status":"ok"}')
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        occupied=server.server_port
        with pytest.raises(RuntimeError):mod.select(occupied,start=0,end=0)
        chosen=mod.select(occupied,start=18841,end=18940)
        assert chosen!=occupied
        assert mod.free(chosen)
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:'+str(occupied)+'/health') as r:
            assert json.load(r)['service']=='africa-credit'
    finally:server.shutdown();server.server_close();thread.join()

def test_port_selection_reuses_running_anyapps():
    import importlib.util,threading
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('port_selector',Path(__file__).parents[1]/'scripts/select-port.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200);self.end_headers();self.wfile.write(b'{"service":"AnyApps","status":"ok"}')
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:assert mod.select(18840,saved=server.server_port)==server.server_port
    finally:server.shutdown();server.server_close();thread.join()

def test_nginx_discovery_matches_explicit_sni_address_groups():
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('routes',Path(__file__).parents[1]/'scripts/repair-nginx-host.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    dump='''# configuration file /etc/nginx/nginx.conf:
# listen 10.0.0.1:443 ssl;
# configuration file /etc/nginx/panel/generated.conf:
server {listen 127.0.0.1:443 ssl; listen 181.214.149.146:443 ssl; listen [::]:443 ssl; listen 443 ssl;}
server {listen 181.214.149.146:80;}
server {listen 10.0.0.2:443 ssl proxy_protocol;}
'''
    assert mod.listen_addresses(dump,443)==['443','127.0.0.1:443','181.214.149.146:443','[::]:443']
    assert mod.listen_addresses(dump,80)==['80','181.214.149.146:80']
    assert Path('/etc/nginx/panel/generated.conf') in mod.active_files(dump)

@pytest.mark.parametrize('hostname,seconds,expected',[
    ('anyapp.olamidepanel.com',604800,True),
    ('another.olamidepanel.com',604800,False),
    ('anyapp.olamidepanel.com',60*86400,False),
])
def test_certificate_hostname_and_expiry_are_independent(tmp_path,hostname,seconds,expected):
    import importlib.util,subprocess
    from pathlib import Path
    certificate=tmp_path/'cert.pem'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(tmp_path/'key.pem'),'-out',str(certificate),'-days','30','-subj','/CN=anyapp.olamidepanel.com','-addext','subjectAltName=DNS:anyapp.olamidepanel.com'],check=True,capture_output=True)
    spec=importlib.util.spec_from_file_location('cert_check',Path(__file__).parents[1]/'scripts/check-certificate.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    result=mod.check(certificate,hostname,seconds)
    assert result['valid'] is expected
    assert result['hostname_valid'] is (hostname=='anyapp.olamidepanel.com')
    assert result['expiry_valid'] is (seconds<30*86400)
