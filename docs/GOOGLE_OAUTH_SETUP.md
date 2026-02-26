# Google OAuth SSO Setup

To enable "Continue with Google" login, you need to configure Google OAuth credentials.

## 1. Create Google OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Select or create a project
3. Click **Create Credentials** → **OAuth client ID**
4. If prompted, configure the OAuth consent screen:
   - User type: **External** (for any Google account) or **Internal** (for workspace only)
   - Add app name, support email, developer contact
5. Application type: **Web application**
6. Name: e.g. `Heliox Dev`
7. **Authorized redirect URIs** — add:
   - Local: `http://localhost:8000/api/v1/auth/google/callback`
   - Production: `https://your-api-domain.com/api/v1/auth/google/callback`
8. Click **Create** and copy the **Client ID** and **Client Secret**

## 2. Configure Backend

Add to `backend/.env` or your environment:

```env
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
FRONTEND_URL=http://localhost:3000
```

## 3. Restart Backend

```bash
docker compose restart api
```

## 4. Verify

- Login page → "Continue with Google" → Enter Team ID → Should redirect to Google
- Or check: `curl http://localhost:8000/api/v1/auth/google/test`

## Troubleshooting

| Error | Fix |
|-------|-----|
| Missing required parameter: client_id | GOOGLE_CLIENT_ID not set in backend env |
| redirect_uri_mismatch | Add exact redirect URI to Google Console |
| Access blocked | Check OAuth consent screen is configured |
