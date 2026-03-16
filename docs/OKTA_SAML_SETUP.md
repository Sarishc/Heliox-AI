# Okta SAML SSO Setup

Configure Okta as the identity provider (IdP) for Heliox team SSO.

## Prerequisites

- Team owner or admin access in Heliox
- Okta admin account (or Okta developer org)

## 1. Create Okta Application

1. In Okta Admin: **Applications** → **Create App Integration**
2. Choose **SAML 2.0**
3. Name: e.g. `Heliox`
4. Click **Next**

## 2. Configure SAML

**General Settings:**
- App name: `Heliox`
- Logo: optional
- Visibility: Show in Okta dashboard

**Configure SAML:**
- **Single sign-on URL (ACS):** `https://your-api-domain.com/api/v1/auth/saml/acs`
  - Local: `http://localhost:8000/api/v1/auth/saml/acs`
- **Audience URI (SP Entity ID):** `https://your-api-domain.com/api/v1/auth/saml/metadata`
  - Local: `http://localhost:8000/api/v1/auth/saml/metadata`
- **Name ID format:** EmailAddress
- **Application username:** Email
- **Attribute statements (optional):**
  - `email` → `user.email`
  - `name` → `user.firstName` + `user.lastName`

## 3. Get IdP Metadata from Okta

After creating the app:
- **Sign On** tab → copy:
  - **Identity Provider single sign-on URL**
  - **Identity Provider issuer**
  - **X.509 Certificate** (download or copy PEM)

## 4. Configure Heliox

1. Log in to Heliox as team owner/admin
2. Go to **Settings** → **Authentication**
3. In **SAML / Okta SSO**:
   - **IdP Entity ID:** paste the Identity Provider issuer (e.g. `http://www.okta.com/...`)
   - **IdP SSO URL:** paste the single sign-on URL
   - **IdP X.509 Certificate:** paste the full PEM (including `-----BEGIN CERTIFICATE-----` and `-----END CERTIFICATE-----`)
   - **Default role:** Viewer (or Admin for new JIT users)
   - Click **Save SAML Config**

## 5. Configure Okta with SP Metadata (optional)

If Okta supports metadata URL:
- Use: `https://your-api-domain.com/api/v1/auth/saml/metadata?team_id=YOUR_TEAM_ID`

Otherwise, configure the ACS URL and Entity ID manually as in step 2.

## 6. Test

1. Log out of Heliox
2. Go to `/login`
3. Click **Continue with Google** (or **Continue with Okta**)
4. Enter your Team ID
5. Click **Continue with Okta**
6. You should redirect to Okta, authenticate, and return to Heliox

## 7. Domain Allowlist (optional)

In **Settings** → **Authentication**:
- Enable **Enforce Domain Restriction**
- Add allowed domains: `company.com`
- Only users with emails from these domains can login via SSO

## Troubleshooting

| Error | Fix |
|-------|-----|
| SAML library not available | Install `python3-saml` and system deps: `libxml2-dev libxmlsec1-dev libxmlsec1-openssl` |
| Invalid or expired | SAML state expires in 10 min. Retry login. |
| Email domain not allowed | Add domain in Settings or disable enforce domain |
| Certificate invalid | Ensure full PEM including BEGIN/END lines |

## Environment

Set in production:
- `API_BASE_URL` – Base URL of your API (e.g. `https://api.heliox.ai`)
