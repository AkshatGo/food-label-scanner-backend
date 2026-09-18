# Mobile release and Replit deployment

## Target
Installable mobile web app (PWA), with a single FastAPI server and OCR worker.
No App Store or Play Store build is included. The same UI works on desktop.
Design rationale and references are in `DESIGN.md`.

## Hosting
Use Replit Reserved VM, one instance and **one Uvicorn worker**. OCR jobs and
photos are persisted before acceptance, then processed serially by the production
worker. Incomplete jobs are replayed on restart with a stable product ID.
Do not use Autoscale, multiple workers or rolling replicas with this worker model;
a distributed queue with leases is required before horizontal scaling.

Import the GitHub repository into Replit. Install `requirements.lock` and ensure
`tesseract --version` succeeds. `.replit` and `replit.nix` supply startup and system
dependency configuration; verify the selected VM deployment in the Publishing UI.
The public server listens on `0.0.0.0:8080`. Browser visits to `/` redirect to `/ui`.

Set these through Replit Secrets (never commit live values):

- `APP_ENV=production` (also set by the production run command)
- `MONGODB_URI`: managed MongoDB TLS connection string, authorized for this host
- `DATABASE_NAME=labelens`
- `JWT_SECRET`: a randomly generated secret, at least 32 characters
- `ALLOWED_ORIGINS`: the exact HTTPS public app origin, no wildcard

Production refuses to start with missing credentials or unavailable MongoDB.
Use managed database backups and verify restore access before storing real data.
Session cookies are HttpOnly, SameSite=Strict and Secure in production. APIs accept
bearer tokens for future native clients. CORS/origin validation and request quotas
are enabled. Quotas currently apply per process: verify the actual Replit proxy
client-IP behavior before relying on them for abuse prevention.

## Mobile behavior
Use HTTPS on physical phones. Camera input supports JPEG, PNG and WEBP; HEIC must
be exported as JPEG. Android browsers can offer an install prompt; iPhone users
can choose Share → Add to Home Screen. The public shell works offline; scans,
history, photos and preferences require connectivity and are never cached by the
service worker. Real camera, keyboard and install flows need physical iOS/Android
acceptance testing before launch.

## Verification
Run `.venv/bin/python -m pytest`. The service provides `/health` for database
readiness. Perform two-account isolation checks and a real-photo scan after publish.
Confirm scan processing survives a controlled app restart against the actual
managed database. Backend tests use memory storage, not a substitute for this check.

## Release gates (not completed merely by deploying)
- Configure and test Replit and managed MongoDB in the owner's accounts.
- Verify deployed OCR binary, TLS, session cookies, domain and database backups.
- Run mobile Safari/Chrome device acceptance and representative real-label OCR QA.
- Have the owner supply privacy/retention terms, support contact, password
  recovery/email delivery, and incident/monitoring ownership. Authenticated data
  export and password-confirmed account deletion are implemented; backup retention
  must be operated separately by the database owner.
- Have qualified reviewers validate the nutrition/personalization rules and the
  current regulatory basis. The embedded formula is explicitly a 2022 draft;
  neither an official endorsement nor a medical/legal certification is claimed.
- Perform load testing and a dependency/security review for the selected runtime.

Until these gates pass, this is a hardened release candidate, not a certified or
fully operated public production service. No cloud resources are provisioned by
the source changes alone.
