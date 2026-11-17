# Deploying login and SSO

Login protects the owner app and every private API. There is no signup endpoint, default account, or default password. Users share one garage. Members can manage vehicles/tickets and use the map; administrators also manage users, SSO and map share links. The independent shared-map service still uses its restricted link instead of an account.

## First administrator

Run this against the same data volume as the API:

```sh
.venv/bin/python -m backend.manage create-admin --email your-admin@example.com
# Docker alternative (once the API container is running):
docker compose exec api python -m backend.manage create-admin --email your-admin@example.com
```

The command asks for a password twice (12+ characters). For automated deployments, use `--password-stdin` and pipe a deployment secret file; never put the password in the command line. The command does not modify cars or tickets. Recovery uses `reset-admin` with the same options; it resets that account's password, restores its administrator access and revokes its sessions/invitations.

Alternatively, set `PARKING_BOOTSTRAP_ADMIN_EMAIL` and `PARKING_BOOTSTRAP_ADMIN_PASSWORD_FILE` (or `PARKING_BOOTSTRAP_ADMIN_PASSWORD`) before the first API startup. Bootstrap only runs if the users table is empty and never overwrites an account. Remove bootstrap credentials afterward. Until configured, the UI shows a setup message and the private APIs remain closed. There is no remotely accessible first-user creation form.

## Configuration

Use `.env.example` as the reference. The native launcher and Compose services load an optional `.env` file; exported process variables take precedence. Environment configuration wins over stored SSO settings. Keep `.env`, secrets and runtime data out of source control.

| Variable | Default / purpose |
|---|---|
| `PARKING_BASE_URL` | `http://127.0.0.1:8000`; exact external owner origin, used for callbacks and invitations. Set the actual HTTPS origin behind a proxy. No trailing path. |
| `PARKING_COOKIE_SECURE` | Automatically true with an HTTPS base URL; may force true for local TLS. Cannot disable Secure on an HTTPS base URL. |
| `PARKING_SESSION_HOURS` | 8; absolute session lifetime in hours (1–168). |
| `PARKING_OIDC_ISSUER` | Exact issuer from discovery, including its trailing slash. Any explicit OIDC option makes this provider managed by deployment configuration. |
| `PARKING_OIDC_DISCOVERY_URL` | Issuer + `/.well-known/openid-configuration`; override for providers whose discovery path differs from their issuer. |
| `PARKING_OIDC_CLIENT_ID` | Registered OIDC client ID. |
| `PARKING_OIDC_CLIENT_SECRET_FILE` | Mounted secret file; preferred over `PARKING_OIDC_CLIENT_SECRET`. |
| `PARKING_OIDC_NAME` | Login button label; default “Single sign-on”. |
| `PARKING_OIDC_ENABLED` | true when an environment issuer is configured. false temporarily disables SSO without deleting settings. |
| `PARKING_OIDC_AUTH_METHOD` | `client_secret_basic`, `client_secret_post`, or `none` for public PKCE clients. |
| `PARKING_AUTH_KEY_FILE` | `data/auth.key`; automatically generated with mode 0600. Encrypts provider configuration stored in SQLite. |
| `PARKING_AUTH_KEY` | Optional Fernet key managed as a deployment secret instead of a key file. |

For UI configuration, sign in as admin and open **Settings → Single sign-on**. Enter the provider label, exact issuer, discovery URL, client ID and secret. Blank secret preserves the saved one. Register the displayed callback URL at the provider. Save and test in another browser before ending the recovery admin session. Existing local passwords remain available if the provider is unavailable.

For multiple API replicas, share the same SQLite-compatible local deployment, encryption key and configuration; SQLite is intended for this small single-host app. Protect the data directory, encryption key and backups with deployment permissions. Back up `auth.key` together with the database; losing it makes saved SSO settings unreadable. You may still use environment-managed SSO or the recovery CLI. Do not synchronize an open SQLite database over a file sync service.

## Authentik

Create an **OAuth2/OpenID Connect provider** and application. Use authorization code flow, a signing certificate/key, and the standard `openid`, `email`, `profile` scopes. Configure a strict redirect URI:

```text
https://parking.example.com/api/auth/oidc/callback
```

With Authentik's recommended per-provider issuer mode, use:

```text
Issuer:    https://auth.example.com/application/o/curbwatch/
Discovery: https://auth.example.com/application/o/curbwatch/.well-known/openid-configuration
```

If using global issuer mode, the issuer is the instance root but discovery stays under the application path; configure both explicitly. Copy the exact issuer from discovery. Require verified email for initial account linking: recent Authentik versions default `email_verified` to false. Configure email verification and an email scope mapping that reflects the real verification status. Do not simply claim all addresses are verified unless your identity administration process actually guarantees that.

Sources: [Authentik OIDC provider and issuer modes](https://docs.goauthentik.io/add-secure-apps/providers/oauth2/), [Authentik verified email configuration](https://docs.goauthentik.io/add-secure-apps/providers/oauth2/verify-email-address/).

Other OIDC providers (for example Keycloak or an Authentik broker) use the same discovery/client settings. This version supports one provider at a time; native SAML and LDAP are not implemented.

## Invitations and account policy

In **Settings → People & access**, add an email, optional name, and role. Copy the generated invitation and deliver it privately. It expires after seven days, works once, and is stored only as a hash. No invitation emails are sent automatically. A new invitation invalidates the previous one. The invited person sets a local password, or can sign in through SSO using that verified email; SSO never creates an unapproved account. After the initial verified email match, the account is bound to the provider's issuer + subject. A different subject cannot take over an already linked email.

Disable an account to revoke its sessions and outstanding invitations immediately. Role changes also end existing sessions. At least one active administrator must remain. Administrators can renew an active user's invitation for password recovery; accepting it replaces local credentials and ends previous sessions. Local CLI reset is available if all admins lose access.

## Proxy and security behavior

Keep both services local until you choose to deploy. For deployment, put the owner API behind trusted HTTPS and set `PARKING_BASE_URL`; configure your reverse proxy to forward only the intended hostname. The app uses this configured origin for redirects and origin checks, rather than trusting incoming Host/forwarded headers. Allow the provider's standard GET/query callback (not form-post). Cookies are HttpOnly, SameSite=Lax and Secure on HTTPS. Writes require JSON, same-origin checks, and an unpredictable per-session CSRF header. Do not log authorization headers, cookies, invitation fragments or callback query strings. The included owner launch commands disable access logs so authorization codes are not recorded; configure proxy logging accordingly.

OIDC uses code + PKCE S256, ten-minute single-use browser-bound state, nonce, provider signature keys, and issuer/audience/expiry checks. Only asymmetric signed ID tokens are accepted. Provider access/ID tokens are discarded after login, not exposed to the browser. Sign out ends the local app session; it does not sign out of the identity provider. Provider-wide/front-channel/back-channel logout is not implemented. App disable/revoke checks take effect on every API request; provider-side revocation alone takes effect when the app session expires or the app account is disabled.

The PWA caches only public shell/OCR assets, never data APIs. Private snapshots are no longer persisted; legacy snapshots and the tab's private drafts are cleared on sign-out/account changes. A fresh/offline launch requires a successful session check before showing private data. An already open authenticated page may remain visible during a network interruption; server access always requires a live valid session. Browser tabs clear their private UI when notified of logout or on the next session check.

Private API documentation also requires login. The separate read-only map server contains no account management or private APIs and continues to validate its own restricted tokens. See `docs/api/auth-contract.md`, `docs/api/openapi.json` and `docs/api/shared-openapi.json` for contracts.
