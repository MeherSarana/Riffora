# Discord dashboard sign-in

The dashboard now uses Discord OAuth2 sign-in. Only the Discord account whose user ID is set in `DASHBOARD_OWNER_ID` can sign in. The dashboard shows servers where that account owns the server or has Administrator / Manage Server permission, and where the music bot is also a member.

## Configure Discord OAuth2

1. Open your application in the [Discord Developer Portal](https://discord.com/developers/applications) and open **OAuth2**.
2. Add this exact redirect URL under **Redirects**:

   ```text
   http://127.0.0.1:5173/api/auth/callback
   ```

3. Copy the application's Client ID and Client Secret into the local `.env` file. Also set `DASHBOARD_OWNER_ID` to your personal Discord user ID (enable Developer Mode in Discord, then right-click your user and choose **Copy User ID**).
4. Set `DISCORD_REDIRECT_URI` to the same redirect URL, then restart the backend.
5. Start the frontend and backend as usual and open `http://127.0.0.1:5173`. Select **Continue with Discord** and authorize the `identify` and `guilds` scopes.

Example `.env` entries (fill these locally; do not commit `.env` or share the Client Secret):

```env
DISCORD_CLIENT_ID=your_application_client_id
DISCORD_CLIENT_SECRET=your_application_client_secret
DASHBOARD_OWNER_ID=your_personal_discord_user_id
DISCORD_REDIRECT_URI=http://127.0.0.1:5173/api/auth/callback
SESSION_COOKIE_SECURE=false
SESSION_TTL_SECONDS=43200
```

For local HTTP development, `SESSION_COOKIE_SECURE=false` is required. Set it to `true` when serving the dashboard over HTTPS. OAuth sessions are held in backend memory and expire after the configured TTL; restarting the backend signs the dashboard out. The Discord OAuth access token stays on the backend and is revoked on sign-out.

`/api/auth/status` is public to the login screen. The remaining `/api` routes and `/ws` player socket require the session cookie and server-management permission. `/health` is the only public health endpoint.
