# AnyApps

**No idea is too small. Bring yours to life.**

Idea-to-app studio for Olamidepanel. Default package: **$999 USD**, one project with five AI browser-app builds/revisions, free static hosting, an available `yourname.olamidepanel.com` subdomain and free store listing submission. Default delivery target: **seven calendar days after verified payment**. Administrators control package prices, credits, availability and delivery targets. Delivery changes and missed targets create customer dashboard notifications.

## Included in this implementation

- Responsive branded website, Android client, account registration/sign-in and private project workspaces.
- Visual layout editor: draggable/tappable blocks, movable/resizable elements, text editing, color styling, freehand touch sketches and undo. Saved layouts and sketches are included in AI build requests.
- OpenAI Responses API generation using an existing server-side `OPENAI_API_KEY`; bounded output and no execution of generated code on the server.
- Private sandboxed previews, downloadable source ZIPs, paid credit ledger, failed/interrupted build refunds and duplicate-build prevention.
- Stripe Checkout with signed webhook verification; Paystack and Flutterwave hosted checkout with server-side transaction verification. USD merchant support must be enabled by the provider. Gateways start disabled until configured and tested.
- Marketplace package checkout and moderated community showcase. Paid third-party listings, seller payouts, PayPal, subscriptions and automatic refunds are **not implemented**.
- Admin dashboard: accounts, manual credits, suspension, password reset, packages, prices, delivery management with notices, listing moderation, hosting suspension, payment records, AI model and gateway toggles, integration readiness and audit log.
- Dedicated systemd services, SQLite online predeployment backup, protected environment configuration, nginx validation/rollback, health check and optional wildcard subdomain hosting.
- Terms, privacy and copyright pages describing the implemented behavior. Operator contact and business identity should be confirmed before accepting public orders.

## Deploy on the Debian 12 Olamidepanel server

Run from the hosting server as root (not this development container):

```bash
git clone https://github.com/olamidebello/Any-App.git /opt/anyapps/repo
cd /opt/anyapps/repo
sudo bash scripts/deploy.sh -e anyapps_existing_env_file=/absolute/path/to/existing/server.env
```

Use the actual server file that contains your existing AI key; never paste its content into chat. The script copies only supported credential fields into `/etc/anyapps/anyapps.env`, preserves existing AnyApps values and never prints keys. If no key is available, the UI remains usable but builds are not charged or queued.

The script pulls `main` without overwriting local modifications, installs dependencies and starts services on **127.0.0.1:18840**. It creates no DNS records. Point `anyapp.olamidepanel.com` at the host. Default TLS paths:

```
/etc/letsencrypt/live/olamidepanel.com/fullchain.pem
/etc/letsencrypt/live/olamidepanel.com/privkey.pem
```

The certificate must cover `anyapp.olamidepanel.com`. Override `anyapps_tls_cert` and `anyapps_tls_key` when using a dedicated certificate. A missing or mismatched certificate now triggers a dedicated HTTP-01 certificate request for `anyapp.olamidepanel.com` using Certbot. DNS must point to this host and port 80 must be reachable. Set `anyapps_tls_email` to receive certificate account notices. No DNS records are changed. The playbook verifies the public HTTPS health response and AnyApps homepage before reporting success.

Create your first administrator interactively:

```bash
sudo /opt/anyapps/repo/scripts/admin.sh
```

No default credentials are shipped. Secrets remain in `/etc/anyapps/anyapps.env`; database and customer data remain in `/var/lib/anyapps`, outside Git. Restart both services after changing credentials:

```bash
sudo systemctl restart anyapps anyapps-worker
```

### Free generated-app hosting

After wildcard DNS `*.olamidepanel.com` and a matching wildcard certificate exist, enable static project hosting:

```bash
sudo bash scripts/deploy.sh -e anyapps_enable_project_hosting=true
```

Inspect existing wildcard/regex nginx vhosts before enabling; exact-name existing domains take precedence. Generated HTML lives in `/srv/anyapps-sites/<slug>/index.html`. The worker marks a deployment live only after the expected public HTTPS URL returns the exact generated HTML. Pending DNS/TLS failures remain visible and retry automatically. HTML is capped at 1 MB. No external script, connection or form submission is permitted by the generated hosting CSP. Account cookies remain scoped to the control-plane hostname. This release builds static/browser-local apps: it does **not** provision arbitrary backend code, databases, payment collection inside generated apps or full native apps from arbitrary ideas. Such work needs implementation and scope review before being sold as complete.

### Payments

Set existing merchant keys in the protected environment, restart services, then enable a gateway in Admin → AI & integrations. Do not enable live sales until merchant onboarding, test checkout, refund support and business contact details are ready. Configure Stripe's webhook to:

```
https://anyapp.olamidepanel.com/payments/stripe/webhook
```

Events: `checkout.session.completed`, `checkout.session.async_payment_succeeded`. Set `STRIPE_WEBHOOK_SECRET`. Payment fulfillment checks reference, total and currency, runs transactionally and grants credits once. Browser return alone does not prove payment. Paystack/Flutterwave orders can be reconciled by returning to `/payments/return/<order-id>` while signed in; unlike Stripe, automatic webhook fulfillment for those two providers is not included. Refunds are handled through the merchant dashboard; reconcile credits with the operator.

### Android build and downloads

Pushing Android source or its workflow on `main` triggers `.github/workflows/android.yml`. It builds an Android **development APK**, uploads a workflow artifact and publishes it to the `android-development` prerelease. The APK uses temporary debug signing; this is not a production Play Store release and updates can require uninstalling the previous debug build. A persistent privately backed-up signing key is required for production distribution.

Download from the repository prerelease, or install on the web server:

```bash
sudo python3 scripts/install-apk.py
```

The script verifies the published SHA-256 checksum and installs `/var/lib/anyapps/downloads/AnyApps.apk`. The website shows its download button only when that file exists. App URL: `https://anyapp.olamidepanel.com/`. The Android app uses a restricted HTTPS WebView, supports touch sketching and opens external checkout in the system browser. Browser and Android WebView sessions are separate: after checkout, sign in in the browser if needed to confirm the payment, then refresh the app.

Local Android build: JDK 17 and Android SDK platform/build-tools 35; run `ANDROID_HOME=/path/to/sdk bash android/tools/build.sh`. An optional Gradle project is also included; CI uses the dependency-light SDK builder. No private production signing key is included.

### Africa Apps Store

The existing `olamidebello/africanappsstore` source was inspected. Its public hosted-app catalog is backed by `hosted_apps(domain,metadata,visible,updated)` in SQLite. After deploying AnyApps with HTTPS and its APK, publish directly into the existing store on the same host:

```bash
sudo /opt/anyapps/deploy-venv/bin/ansible-playbook -i localhost, -c local ansible/publish-store.yml
```

The publisher discovers the existing `africanappsstore.service` data directory (default `/var/lib/africanappsstore/store.sqlite3`), backs up the database, validates its schema and updates **only** `anyapp.olamidepanel.com`. It preserves any existing visibility setting and every other listing. Override the database by running `scripts/publish-store.py --database /actual/store.sqlite3` directly if the service uses EnvironmentFile-based overrides. It verifies public AnyApps health, the exact public APK checksum and the public store catalog before reporting success. The download is hosted on AnyApps and linked from the store's existing **Hosted apps** view; no store source replacement or restart is necessary.

`store-export.py` and the worker's feed remain available as optional import outputs for future automation. A GitHub push does not itself update the live store database. Direct server access is needed to run the publisher.

## Verify locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest ansible-core
.venv/bin/python -m pytest -q
.venv/bin/ansible-playbook -i localhost, -c local ansible/deploy.yml --syntax-check
COOKIE_SECURE=0 .venv/bin/flask --app app run --port 18840
```

Tests cover privacy/ownership, CSRF, package defaults, build charging/refunds, generated preview isolation, signed webhook validation, amount mismatch rejection, duplicate payment fulfillment and delivery change notifications. AI/payment calls in tests are mocked; no customer funds or live AI credits are consumed.

## Operational limits

Free hosting does not imply unlimited infrastructure. This implementation has no email delivery, automated seller payouts, subscription engine, self-service password recovery, support ticket system or account deletion endpoint. Notifications are in-app. Admin lists show the most recent 200 records. Back up the SQLite database and protect server configuration before scaling. No direct production deployment or public store listing is implied by a GitHub push.

## API references

- https://developers.openai.com/api/reference/resources/responses/methods/create
- https://docs.stripe.com/api/checkout/sessions/create
- https://docs.stripe.com/webhooks/signature
- https://paystack.com/docs/api/transaction/
- https://developer.flutterwave.com/docs/flutterwave-standard-1
- https://developer.flutterwave.com/docs/transaction-verification
- Privacy practice reference: https://www.ftc.gov/business-guidance/resources/protecting-personal-information-guide-business-0

## Repair a domain showing another application

If `anyapp.olamidepanel.com` shows Africa Bulk Hub or another default site, run on the hosting server:

```bash
cd /opt/anyapps/repo
git pull --ff-only
sudo bash scripts/repair-routing.sh
```

This redeploys the dedicated AnyApps vhost. Conflicting exact `server_name` entries for **only** `anyapp.olamidepanel.com` are removed from other active nginx files after taking backups under `/var/backups/anyapps/nginx-*`. Other domain names, routes and services remain in place. An old block with no other name receives an inert `.invalid` name. Wildcard names are preserved; the new exact-name AnyApps vhost takes precedence. If nginx validation fails, prior hostname mappings are restored before any reload. The certificate is reused when valid or a dedicated Certbot certificate is requested. Local hostname routing, public TLS, `/health` service identity and homepage branding are checked. DNS or certificate failures stop deployment with an error rather than claiming the site is live.

Rollback of detached mappings (only if needed): `sudo python3 scripts/repair-nginx-host.py --manifest /var/backups/anyapps/nginx-<checkpoint>/manifest.json --restore`, followed by `sudo nginx -t` and a reload only after successful validation. The timestamped checkpoint records original file paths.
