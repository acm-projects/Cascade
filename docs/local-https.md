# Trusted local HTTPS for Cascade

The local proxy serves **https://localhost:8443** and forwards to FastAPI at **http://127.0.0.1:8000**. Caddy binds only to IPv4/IPv6 loopback. It does not publish content to LinkedIn or change the editor, Instagram or YouTube flows.

## One-time setup on this Mac

Caddy and mkcert are installed with Homebrew:

```sh
brew install mkcert caddy
mkdir -p .local-https
chmod 700 .local-https
mkcert -cert-file .local-https/localhost.pem -key-file .local-https/localhost-key.pem localhost 127.0.0.1 ::1
chmod 600 .local-https/localhost-key.pem
```

The mkcert CA is trusted in the current user's **login keychain**, so no system-wide trust change was necessary. The system-wide `mkcert -install` attempt needed an administrator password and did not complete; user-keychain trust succeeded instead:

```sh
security add-trusted-cert -r trustRoot \
  -k "$HOME/Library/Keychains/login.keychain-db" \
  "$(mkcert -CAROOT)/rootCA.pem"
```

The leaf certificate and private key stay in ignored `.local-https/` with private directory/key permissions. mkcert's CA and CA private key remain in its per-user application-data directory outside the repository. Never commit or share private keys, including `rootCA-key.pem`. Only the public Caddy configuration and launcher belong in Git. To renew the leaf certificate, rerun its generation command above and restart Caddy.

## Start the services

Run these from the Cascade repository root, in **two separate terminals**. Do not start a second copy if the ports are already occupied.

Terminal 1 — FastAPI:

```sh
python3 -m uvicorn app1:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2 — HTTPS proxy:

```sh
sh scripts/start_local_https.sh
```

The launcher sets the absolute certificate directory and runs `scripts/local_https.Caddyfile`. Caddy uses the explicit mkcert certificate; automatic certificate provisioning/redirect listeners and the admin API are disabled. Access logging is off, and request error dumps are excluded to avoid recording OAuth callback codes/state. The FastAPI callback log filters remain in place. Existing long-running renders/uploads pass through Caddy without an added body-size cap or short response timeout.

Open **https://localhost:8443** to use Cascade. Ctrl+C stops each foreground service in its own terminal. No Homebrew background service was enabled.

## Private environment configuration

The setup preserves existing credentials and adds this origin to the existing `CLERK_AUTHORIZED_PARTIES` list:

```ini
CLERK_AUTHORIZED_PARTIES=http://127.0.0.1:8000,http://localhost:8000,https://localhost:8443
LINKEDIN_REDIRECT_URI=https://localhost:8443/api/social/linkedin/callback
```

Preserve any other origins already present in your private `.env`. `.env` changes require a backend restart/reload; editing `.env` alone may not trigger Uvicorn's watcher. Register that **exact** callback URI in LinkedIn Auth → Authorized redirect URLs. Leave the existing Google redirect URI and social credentials intact. LinkedIn client ID/secret and product permissions are configured separately in [linkedin-publishing.md](linkedin-publishing.md).

## Verify without OAuth or publication

On this Mac, use the system curl (it checks the macOS trust store):

```sh
/usr/bin/curl --fail --show-error https://localhost:8443/api/health
/usr/bin/curl --silent --show-error -o /dev/null -w '%{http_code}\n' \
  https://localhost:8443/api/social/linkedin/callback
/usr/bin/curl --silent --show-error -o /dev/null -w '%{http_code}\n' \
  -H 'Origin: https://localhost:8443' https://localhost:8443/api/projects
```

Expected: health 200, no-state callback 400, unauthenticated projects 401. A 403 “Origin not allowed” indicates a missing HTTPS origin or an old backend process that has not reloaded `.env`. Do not use `curl -k` or browser certificate exceptions: those do not prove trusted HTTPS. Python, Homebrew curl, Firefox or other clients with separate CA stores may need their own trust configuration; system curl verification is not a claim that every independent trust store was changed.

Implementation references: [mkcert](https://github.com/FiloSottile/mkcert), [Caddy loopback binding](https://caddyserver.com/docs/caddyfile/directives/bind).
