"""AnyApps control plane. Generated code is stored as data, never executed here."""
from datetime import datetime, timedelta, timezone
import functools, hashlib, hmac, io, json, os, re, secrets, sqlite3, time, uuid, zipfile
from pathlib import Path
from urllib import request as http, parse
import click
from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = Path(__file__).resolve().parent

def create_app(test_config=None):
    app = Flask(__name__)
    if os.environ.get('TRUST_PROXY')=='1': app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1,x_proto=1)
    app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY') or secrets.token_hex(32), DATABASE=os.environ.get('DATABASE',str(ROOT/'instance/anyapps.sqlite3')), MAX_CONTENT_LENGTH=2*1024*1024, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE','1')=='1', PERMANENT_SESSION_LIFETIME=28800)
    if test_config: app.config.update(test_config)
    Path(app.config['DATABASE']).parent.mkdir(parents=True,exist_ok=True)

    def db():
        if 'db' not in g:
            g.db=sqlite3.connect(app.config['DATABASE'],timeout=30,isolation_level=None)
            g.db.row_factory=sqlite3.Row
            g.db.execute('PRAGMA foreign_keys=ON')
        return g.db
    app.db=db
    @app.teardown_appcontext
    def close(_):
        if 'db' in g: g.db.close()
    with app.app_context(): db().executescript((ROOT/'schema.sql').read_text())

    def setting(key,default=''):
        row=db().execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        return row['value'] if row else default
    def audit(action,target=''):
        db().execute('INSERT INTO audit(actor,action,target) VALUES(?,?,?)',(g.user['id'] if g.user else None,action,str(target)))
    def auth(admin=False):
        def deco(fn):
            @functools.wraps(fn)
            def wrapped(*a,**kw):
                if not g.user: return redirect(url_for('login'))
                if admin and g.user['role']!='admin': abort(403)
                return fn(*a,**kw)
            return wrapped
        return deco
    def owned(pid):
        p=db().execute('SELECT * FROM projects WHERE id=? AND user_id=?',(pid,g.user['id'])).fetchone()
        if not p: abort(404)
        return p
    def limited(key,maximum=10,window=900):
        key=hashlib.sha256(key.encode()).hexdigest(); now=int(time.time())
        db().execute('INSERT INTO attempts(key,count,reset) VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=CASE WHEN reset<? THEN 1 ELSE count+1 END,reset=CASE WHEN reset<? THEN excluded.reset ELSE reset END',(key,now+window,now,now))
        if db().execute('SELECT count FROM attempts WHERE key=?',(key,)).fetchone()[0]>maximum: abort(429)
    @app.before_request
    def before():
        g.user=db().execute('SELECT * FROM users WHERE id=? AND active=1',(session.get('uid'),)).fetchone()
        if 'csrf' not in session: session['csrf']=secrets.token_hex(24)
        if request.method=='POST' and request.endpoint not in ('stripe_webhook',):
            if not hmac.compare_digest(session['csrf'],request.form.get('csrf','')): abort(400,'Your form expired. Reload the page and try again.')
    @app.after_request
    def headers(r):
        r.headers['X-Content-Type-Options']='nosniff'
        r.headers['Referrer-Policy']='same-origin'
        r.headers.setdefault('X-Frame-Options','DENY')
        r.headers.setdefault('Content-Security-Policy',"default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; frame-src 'self'; base-uri 'none'; form-action 'self' https://checkout.stripe.com https://checkout.paystack.com https://checkout.flutterwave.com; object-src 'none'")
        if request.path.startswith(('/dashboard','/admin','/projects','/checkout')): r.headers['Cache-Control']='no-store'
        return r
    @app.context_processor
    def context(): return dict(user=g.user,csrf=session.get('csrf'),setting=setting,year=time.gmtime().tm_year)
    @app.get('/health')
    def health():
        db().execute('SELECT 1'); return jsonify(status='ok',service='AnyApps')
    @app.get('/')
    def home(): return render_template('home.html',plans=db().execute('SELECT * FROM plans WHERE active=1').fetchall())
    @app.route('/register',methods=['GET','POST'])
    def register():
        if request.method=='POST':
            if setting('registration_enabled')!='1': abort(403)
            limited('register:'+request.remote_addr,5)
            email=request.form.get('email','').strip().lower(); pw=request.form.get('password',''); name=request.form.get('name','').strip()[:100]
            if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or len(email)>254 or len(pw)<12 or not name or request.form.get('agree')!='yes':
                flash('Enter a valid name, email and password of at least 12 characters, and accept the terms.','error')
            else:
                try:
                    cur=db().execute('INSERT INTO users(email,password,name) VALUES(?,?,?)',(email,generate_password_hash(pw),name)); session.clear(); session['uid']=cur.lastrowid; session.permanent=True
                    return redirect('/dashboard')
                except sqlite3.IntegrityError: flash('Unable to register this email. Try signing in.','error')
        return render_template('auth.html',register=True)
    @app.route('/login',methods=['GET','POST'])
    def login():
        if request.method=='POST':
            limited('login:'+request.remote_addr)
            u=db().execute('SELECT * FROM users WHERE email=? AND active=1',(request.form.get('email','').strip().lower(),)).fetchone()
            if u and check_password_hash(u['password'],request.form.get('password','')):
                session.clear(); session['uid']=u['id']; session.permanent=True; return redirect('/dashboard')
            flash('Email or password was not accepted.','error')
        return render_template('auth.html',register=False)
    @app.post('/logout')
    def logout(): session.clear(); return redirect('/')
    @app.get('/dashboard')
    @auth()
    def dashboard():
        return render_template('dashboard.html',notifications=db().execute('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 20',(g.user['id'],)).fetchall(),projects=db().execute('SELECT * FROM projects WHERE user_id=? ORDER BY created DESC',(g.user['id'],)).fetchall(),orders=db().execute('SELECT * FROM orders WHERE user_id=? ORDER BY created DESC LIMIT 20',(g.user['id'],)).fetchall(),ledger=db().execute('SELECT * FROM ledger WHERE user_id=? ORDER BY id DESC LIMIT 20',(g.user['id'],)).fetchall())
    @app.post('/projects')
    @auth()
    def new_project():
        name=request.form.get('name','').strip()[:100]; idea=request.form.get('idea','').strip()[:12000]; slug=request.form.get('slug','').strip().lower()
        if len(name)<2 or len(idea)<20 or not re.fullmatch(r'[a-z][a-z0-9-]{2,39}',slug) or slug in ('www','mail','admin','api','anyapp','anyapps','support','hosting','panel','ftp','smtp','autodiscover','status','billing'):
            flash('Use a name, a description of at least 20 characters, and a unique 3–40 character subdomain starting with a letter.','error'); return redirect('/dashboard')
        pid=uuid.uuid4().hex
        try: db().execute('INSERT INTO projects(id,user_id,name,idea,slug,style) VALUES(?,?,?,?,?,?)',(pid,g.user['id'],name,idea,slug,request.form.get('style','modern') if request.form.get('style') in ('modern','playful','minimal') else 'modern'))
        except sqlite3.IntegrityError: flash('That subdomain is already reserved. Choose another.','error'); return redirect('/dashboard')
        audit('project.create',pid); return redirect('/projects/'+pid)
    @app.route('/projects/<pid>',methods=['GET','POST'])
    @auth()
    def project(pid):
        p=owned(pid)
        if request.method=='POST':
            idea=request.form.get('idea','').strip()[:12000]
            if len(idea)<20: abort(400)
            db().execute('UPDATE projects SET idea=? WHERE id=?',(idea,pid)); audit('project.edit',pid); return redirect(request.path)
        return render_template('project.html',project=p,delivery=db().execute('SELECT * FROM deliveries WHERE project_id=?',(pid,)).fetchone(),design=db().execute('SELECT * FROM designs WHERE project_id=?',(pid,)).fetchone(),builds=db().execute('SELECT * FROM builds WHERE project_id=? ORDER BY rowid DESC',(pid,)).fetchall(),deployments=db().execute('SELECT * FROM deployments WHERE project_id=? ORDER BY rowid DESC',(pid,)).fetchall())
    @app.post('/projects/<pid>/design')
    @auth()
    def save_design(pid):
        owned(pid)
        try:
            layout=json.loads(request.form.get('layout','[]'))
            if not isinstance(layout,list) or len(layout)>50: raise ValueError()
            for block in layout:
                if not isinstance(block,dict) or block.get('type') not in ('heading','text','button','image','card','input','navigation'): raise ValueError()
                block['text']=str(block.get('text',''))[:300]
                for key in ('x','y','width','height'): block[key]=max(0,min(1600,int(block.get(key,100))))
        except (ValueError,TypeError,json.JSONDecodeError): abort(400,'Invalid layout')
        sketch=request.form.get('sketch','')
        if sketch and (not re.fullmatch(r'data:image/png;base64,[A-Za-z0-9+/=]+',sketch) or len(sketch)>1000000): abort(400,'Invalid or oversized sketch')
        bg=request.form.get('background','#f8f7ff'); accent=request.form.get('accent','#7047eb')
        if not all(re.fullmatch(r'#[0-9a-fA-F]{6}',c) for c in (bg,accent)): abort(400)
        db().execute('INSERT INTO designs(project_id,layout,sketch,background,accent) VALUES(?,?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET layout=excluded.layout,sketch=excluded.sketch,background=excluded.background,accent=excluded.accent,updated=CURRENT_TIMESTAMP',(pid,json.dumps(layout),sketch,bg,accent))
        audit('design.save',pid); flash('Design saved. Your next build will use this layout and sketch.'); return redirect('/projects/'+pid+'#studio')
    @app.post('/projects/<pid>/build')
    @auth()
    def build(pid):
        owned(pid)
        if setting('builds_enabled')!='1' or not os.environ.get('OPENAI_API_KEY'): flash('Build service is not ready. Your credits have not been charged.','error'); return redirect('/projects/'+pid)
        bid=uuid.uuid4().hex
        try:
            db().execute('BEGIN IMMEDIATE')
            if db().execute("SELECT id FROM builds WHERE project_id=? AND status IN ('queued','building')",(pid,)).fetchone(): raise ValueError('A build is already running.')
            if not db().execute('UPDATE users SET balance=balance-1 WHERE id=? AND balance>=1',(g.user['id'],)).rowcount: raise ValueError('Purchase build credits in the marketplace first.')
            db().execute('INSERT INTO builds(id,project_id) VALUES(?,?)',(bid,pid))
            db().execute('INSERT INTO ledger(user_id,delta,reason,reference) VALUES(?,-1,?,?)',(g.user['id'],'App build',bid))
            db().execute("UPDATE projects SET status='queued' WHERE id=?",(pid,)); db().execute('COMMIT'); audit('build.queue',bid)
        except ValueError as e: db().execute('ROLLBACK'); flash(str(e),'error')
        return redirect('/projects/'+pid)
    @app.get('/builds/<bid>/preview')
    @auth()
    def preview(bid):
        b=db().execute('SELECT b.* FROM builds b JOIN projects p ON b.project_id=p.id WHERE b.id=? AND p.user_id=?',(bid,g.user['id'])).fetchone()
        if not b or b['status']!='ready': abort(404)
        r=app.response_class(b['html'],mimetype='text/html')
        # A generated app cannot access the control plane's cookies, network or top-level navigation.
        r.headers['Content-Security-Policy']="sandbox allow-scripts; default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'"
        r.headers['X-Frame-Options']='SAMEORIGIN'; r.headers['Cache-Control']='no-store'; return r
    @app.get('/builds/<bid>/download')
    @auth()
    def download_build(bid):
        b=db().execute('SELECT b.* FROM builds b JOIN projects p ON b.project_id=p.id WHERE b.id=? AND p.user_id=?',(bid,g.user['id'])).fetchone()
        if not b or b['status']!='ready': abort(404)
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z: z.writestr('index.html',b['html']); z.writestr('README.txt','Generated by AnyApps. Review before publishing. This is a browser app; backend integrations require separate development.')
        out.seek(0); return send_file(out,as_attachment=True,download_name='AnyApps-'+bid[:8]+'.zip',mimetype='application/zip')
    @app.post('/projects/<pid>/publish')
    @auth()
    def publish(pid):
        p=owned(pid); b=db().execute("SELECT * FROM builds WHERE project_id=? AND status='ready' ORDER BY rowid DESC LIMIT 1",(pid,)).fetchone()
        if not b: abort(400,'Build an app before publishing.')
        if not os.environ.get('PUBLISH_ROOT'): flash('Hosting is awaiting server provisioning. Your build is available to download.','error'); return redirect('/projects/'+pid)
        if db().execute("SELECT id FROM deployments WHERE project_id=? AND status='pending'",(pid,)).fetchone(): flash('A publication is already queued.'); return redirect('/projects/'+pid)
        db().execute('INSERT INTO deployments(id,project_id,build_id,url) VALUES(?,?,?,?)',(uuid.uuid4().hex,pid,b['id'],'https://'+p['slug']+'.olamidepanel.com')); audit('publish.request',pid); flash('Publication queued. The deployment worker will verify HTTPS before marking it live.'); return redirect('/projects/'+pid)
    @app.get('/marketplace')
    def marketplace(): return render_template('marketplace.html',plans=db().execute('SELECT * FROM plans WHERE active=1').fetchall(),listings=db().execute("SELECT l.*,p.slug FROM listings l JOIN projects p ON p.id=l.project_id WHERE l.status='approved' AND p.public=1").fetchall(),gateways=available_gateways(),projects=db().execute('SELECT * FROM projects WHERE user_id=?',(g.user['id'],)).fetchall() if g.user else [])
    def available_gateways():
        return [k for k,env in [('stripe','STRIPE_SECRET_KEY'),('paystack','PAYSTACK_SECRET_KEY'),('flutterwave','FLUTTERWAVE_SECRET_KEY')] if setting(k+'_enabled')=='1' and os.environ.get(env)]
    @app.post('/projects/<pid>/list')
    @auth()
    def list_project(pid):
        p=owned(pid)
        if not db().execute("SELECT 1 FROM builds WHERE project_id=? AND status='ready'",(pid,)).fetchone(): abort(400,'A completed build is required.')
        if not db().execute("SELECT 1 FROM listings WHERE project_id=? AND status IN ('pending','approved')",(pid,)).fetchone(): db().execute('INSERT INTO listings(owner_id,project_id,name,description) VALUES(?,?,?,?)',(g.user['id'],pid,p['name'],p['idea']))
        audit('listing.submit',pid); flash('Submitted for marketplace review. Africa Apps Store publication is tracked separately.'); return redirect('/projects/'+pid)
    @app.post('/checkout/<int:plan_id>')
    @auth()
    def checkout(plan_id):
        plan=db().execute('SELECT * FROM plans WHERE id=? AND active=1',(plan_id,)).fetchone(); provider=request.form.get('provider')
        if not plan or provider not in available_gateways(): abort(400,'Choose an enabled payment provider.')
        pid=request.form.get('project_id',''); owned(pid)
        oid=uuid.uuid4().hex
        db().execute('INSERT INTO orders(id,user_id,plan_id,amount,credits,provider) VALUES(?,?,?,?,?,?)',(oid,g.user['id'],plan_id,plan['price'],plan['credits'],provider))
        db().execute('INSERT INTO order_projects VALUES(?,?,?)',(oid,pid,int(setting('delivery_days','7'))))
        base=os.environ.get('PUBLIC_URL','https://anyapp.olamidepanel.com').rstrip('/')
        try:
            if provider=='stripe':
                import stripe
                s=stripe.checkout.Session.create(api_key=os.environ['STRIPE_SECRET_KEY'],idempotency_key=oid,mode='payment',client_reference_id=oid,customer_email=g.user['email'],line_items=[{'price_data':{'currency':'usd','product_data':{'name':'AnyApps '+plan['name']},'unit_amount':plan['price']},'quantity':1}],success_url=base+'/payments/return/'+oid,cancel_url=base+'/marketplace')
                ref=s.id; target=s.url
            elif provider=='paystack':
                r=api('https://api.paystack.co/transaction/initialize',os.environ['PAYSTACK_SECRET_KEY'],{'email':g.user['email'],'amount':plan['price'],'currency':'USD','reference':oid,'callback_url':base+'/payments/return/'+oid})
                ref=oid; target=r['data']['authorization_url']
            else:
                r=api('https://api.flutterwave.com/v3/payments',os.environ['FLUTTERWAVE_SECRET_KEY'],{'tx_ref':oid,'amount':str(plan['price']/100),'currency':'USD','redirect_url':base+'/payments/return/'+oid,'customer':{'email':g.user['email']},'customizations':{'title':'AnyApps '+plan['name']}})
                ref=oid; target=r['data']['link']
            if parse.urlparse(target).hostname not in ('checkout.stripe.com','checkout.paystack.com','checkout.flutterwave.com'): raise ValueError('Unexpected checkout domain')
            db().execute('UPDATE orders SET provider_ref=? WHERE id=?',(ref,oid)); return redirect(target,303)
        except Exception:
            app.logger.warning('Checkout failed for order %s',oid); flash('The payment provider could not start checkout. No build credits were issued.','error'); return redirect('/marketplace')
    def fulfill(oid,ref,amount,currency):
        try:
            db().execute('BEGIN IMMEDIATE'); o=db().execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
            if not o or o['provider_ref']!=ref or o['amount']!=amount or currency.lower()!=o['currency']: raise ValueError('Payment does not match order')
            if o['status']!='paid':
                db().execute("UPDATE orders SET status='paid' WHERE id=?",(oid,)); db().execute('UPDATE users SET balance=balance+? WHERE id=?',(o['credits'],o['user_id'])); db().execute('INSERT INTO ledger(user_id,delta,reason,reference) VALUES(?,?,?,?)',(o['user_id'],o['credits'],'Package purchase',oid))
                op=db().execute('SELECT * FROM order_projects WHERE order_id=?',(oid,)).fetchone()
                if op:
                    due=(datetime.now(timezone.utc)+timedelta(days=op['delivery_days'])).strftime('%Y-%m-%d')
                    db().execute('INSERT INTO deliveries(project_id,due) VALUES(?,?) ON CONFLICT(project_id) DO NOTHING',(op['project_id'],due))
                    db().execute('INSERT INTO notifications(user_id,message) VALUES(?,?)',(o['user_id'],'Payment confirmed. Your app delivery target is '+due+'. We will notify you here if it changes.'))
            db().execute('COMMIT')
        except Exception:
            db().execute('ROLLBACK'); raise
    @app.get('/payments/return/<oid>')
    @auth()
    def payment_return(oid):
        o=db().execute('SELECT * FROM orders WHERE id=? AND user_id=?',(oid,g.user['id'])).fetchone()
        if not o or not o['provider_ref']: abort(404)
        try:
            if o['provider']=='stripe':
                import stripe
                r=stripe.checkout.Session.retrieve(o['provider_ref'],api_key=os.environ['STRIPE_SECRET_KEY'])
                if r.payment_status=='paid': fulfill(oid,r.id,r.amount_total,r.currency)
            elif o['provider']=='paystack':
                r=api('https://api.paystack.co/transaction/verify/'+parse.quote(o['provider_ref'],safe=''),os.environ['PAYSTACK_SECRET_KEY'])['data']
                if r['status']=='success': fulfill(oid,r['reference'],int(r['amount']),r['currency'])
            elif o['provider']=='flutterwave':
                tx=request.args.get('transaction_id','')
                if not tx.isdigit(): raise ValueError('Missing transaction')
                r=api('https://api.flutterwave.com/v3/transactions/'+tx+'/verify',os.environ['FLUTTERWAVE_SECRET_KEY'])['data']
                if r['status']=='successful': fulfill(oid,r['tx_ref'],round(float(r['amount'])*100),r['currency'])
            flash('Payment checked. Your dashboard shows the confirmed order and credit balance.')
        except Exception: flash('Payment is awaiting verification. Do not pay again; contact support with order '+oid,'error')
        return redirect('/dashboard')
    @app.post('/payments/stripe/webhook')
    def stripe_webhook():
        import stripe
        secret=os.environ.get('STRIPE_WEBHOOK_SECRET')
        if not secret: abort(503)
        try: event=stripe.Webhook.construct_event(request.get_data(),request.headers.get('Stripe-Signature',''),secret)
        except Exception: abort(400)
        if event['type'] in ('checkout.session.completed','checkout.session.async_payment_succeeded'):
            r=event['data']['object']
            if r['payment_status']=='paid':
                try: fulfill(r['client_reference_id'],r['id'],r['amount_total'],r['currency'])
                except ValueError: abort(400)
        return jsonify(received=True)
    @app.get('/admin')
    @auth(admin=True)
    def admin():
        tables={k:db().execute('SELECT * FROM '+k+' ORDER BY rowid DESC LIMIT 200').fetchall() for k in ('users','plans','projects','builds','orders','listings','deployments','deliveries','audit')}
        ready={k:bool(os.environ.get(k)) for k in ('OPENAI_API_KEY','STRIPE_SECRET_KEY','STRIPE_WEBHOOK_SECRET','PAYSTACK_SECRET_KEY','FLUTTERWAVE_SECRET_KEY','PUBLISH_ROOT','STORE_EXPORT_ROOT')}
        return render_template('admin.html',tables=tables,ready=ready)
    @app.post('/admin/settings')
    @auth(admin=True)
    def admin_settings():
        for k in ('builds_enabled','registration_enabled','stripe_enabled','paystack_enabled','flutterwave_enabled'): db().execute('UPDATE settings SET value=? WHERE key=?',('1' if request.form.get(k)=='on' else '0',k))
        try: days=int(request.form.get('delivery_days','7'))
        except ValueError: abort(400)
        if not 1<=days<=365: abort(400)
        db().execute("UPDATE settings SET value=? WHERE key='delivery_days'",(str(days),))
        model=request.form.get('ai_model','').strip()
        if re.fullmatch(r'[A-Za-z0-9._:-]{1,100}',model): db().execute('UPDATE settings SET value=? WHERE key=\'ai_model\'',(model,))
        audit('settings.update'); flash('Settings saved. Credentials remain in the server environment.'); return redirect('/admin#settings')
    @app.post('/admin/users/<int:uid>')
    @auth(admin=True)
    def admin_user(uid):
        if uid==g.user['id']: abort(400,'Use another administrator to change this account.')
        action=request.form.get('action'); u=db().execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        if not u: abort(404)
        if action in ('suspend','activate'): db().execute('UPDATE users SET active=? WHERE id=?',(int(action=='activate'),uid))
        elif action=='credit':
            try: credits=int(request.form.get('credits','0'))
            except ValueError: abort(400)
            if not 1<=credits<=10000: abort(400)
            db().execute('BEGIN IMMEDIATE'); db().execute('UPDATE users SET balance=balance+? WHERE id=?',(credits,uid)); db().execute('INSERT INTO ledger(user_id,delta,reason,reference) VALUES(?,?,?,?)',(uid,credits,'Admin credit',uuid.uuid4().hex)); db().execute('COMMIT')
        elif action=='reset':
            pw=request.form.get('password','')
            if len(pw)<12: abort(400)
            db().execute('UPDATE users SET password=? WHERE id=?',(generate_password_hash(pw),uid))
        else: abort(400)
        audit('user.'+action,uid); flash('Account updated.'); return redirect('/admin#users')
    @app.post('/admin/plans')
    @auth(admin=True)
    def admin_plan():
        try: price=int(request.form['price']); credits=int(request.form['credits'])
        except (ValueError,KeyError): abort(400)
        if not 0<=price<=10000000 or not 1<=credits<=10000: abort(400)
        name=request.form.get('name','').strip()[:80]; desc=request.form.get('description','').strip()[:500]
        if not name or not desc: abort(400)
        if request.form.get('id'): db().execute('UPDATE plans SET name=?,description=?,price=?,credits=?,active=? WHERE id=?',(name,desc,price,credits,int(request.form.get('active')=='on'),request.form['id']))
        else: db().execute('INSERT INTO plans(name,description,price,credits) VALUES(?,?,?,?)',(name,desc,price,credits))
        audit('plan.save',name); flash('Package saved. Existing orders keep their original prices.'); return redirect('/admin#plans')
    @app.post('/admin/listings/<int:lid>')
    @auth(admin=True)
    def admin_listing(lid):
        status=request.form.get('status')
        if status not in ('approved','rejected','pending'): abort(400)
        l=db().execute('SELECT * FROM listings WHERE id=?',(lid,)).fetchone()
        if not l: abort(404)
        db().execute('UPDATE listings SET status=? WHERE id=?',(status,lid)); db().execute('UPDATE projects SET public=? WHERE id=?',(int(status=='approved'),l['project_id'])); audit('listing.'+status,lid); return redirect('/admin#listings')
    @app.post('/admin/deliveries/<pid>')
    @auth(admin=True)
    def admin_delivery(pid):
        p=db().execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
        if not p: abort(404)
        due=request.form.get('due',''); note=request.form.get('note','').strip()[:1000]; status=request.form.get('status','scheduled')
        try: datetime.strptime(due,'%Y-%m-%d')
        except ValueError: abort(400)
        if not note or status not in ('scheduled','in_progress','delayed','delivered'): abort(400,'Provide a change notice and valid status.')
        db().execute('BEGIN IMMEDIATE')
        db().execute('INSERT INTO deliveries(project_id,due,status,note) VALUES(?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET due=excluded.due,status=excluded.status,note=excluded.note,updated=CURRENT_TIMESTAMP',(pid,due,status,note))
        db().execute('INSERT INTO notifications(user_id,message) VALUES(?,?)',(p['user_id'],p['name']+': delivery '+status.replace('_',' ')+'. Target: '+due+'. '+note))
        db().execute('COMMIT'); audit('delivery.change',pid); flash('Delivery updated and customer notified in their dashboard.'); return redirect('/admin#deliveries')
    @app.post('/admin/deployments/<did>/suspend')
    @auth(admin=True)
    def admin_suspend(did):
        d=db().execute('SELECT * FROM deployments WHERE id=?',(did,)).fetchone()
        if not d: abort(404)
        db().execute("UPDATE deployments SET status='suspend_requested' WHERE project_id=? AND status='live'",(d['project_id'],)); audit('hosting.suspend',did); flash('Suspension queued for the hosting worker.'); return redirect('/admin#hosting')
    @app.get('/download')
    def download(): return render_template('download.html',available=Path(os.environ.get('APK_PATH', '/var/lib/anyapps/downloads/AnyApps.apk')).is_file())
    @app.get('/download/android')
    def android_download():
        p=Path(os.environ.get('APK_PATH', '/var/lib/anyapps/downloads/AnyApps.apk'))
        if not p.is_file(): abort(404,'Android release has not been installed on this server yet.')
        return send_file(p,as_attachment=True,download_name='AnyApps.apk',mimetype='application/vnd.android.package-archive')
    @app.get('/legal/<kind>')
    def legal(kind):
        if kind not in ('terms','privacy','copyright'): abort(404)
        return render_template('legal.html',kind=kind)
    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(429)
    def error(e): return render_template('error.html',error=e),e.code
    @app.cli.command('create-admin')
    @click.option('--email',prompt=True)
    @click.option('--password',prompt=True,hide_input=True,confirmation_prompt=True)
    def create_admin(email,password):
        if len(password)<12: raise click.ClickException('Use at least 12 characters.')
        try: db().execute("INSERT INTO users(email,password,name,role) VALUES(?,?,?,'admin')",(email.lower().strip(),generate_password_hash(password),'Administrator'))
        except sqlite3.IntegrityError: raise click.ClickException('Email already exists. No changes made.')
        click.echo('Administrator created.')
    @app.cli.command('worker')
    @click.option('--once',is_flag=True)
    def worker(once):
        from worker import run
        run(app,once)
    return app

def api(url,key,data=None):
    body=json.dumps(data).encode() if data is not None else None
    req=http.Request(url,data=body,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','User-Agent':'AnyApps/1.0'})
    with http.urlopen(req,timeout=120) as r: return json.load(r)

if __name__=='__main__': create_app().run(host='127.0.0.1',port=18840)
