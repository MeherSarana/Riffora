---
title: Riffora Privacy Policy
permalink: /privacy-policy
---

<!-- Draft: replace the contact placeholder and review this policy against the actual hosting setup before publishing. -->

# Riffora Privacy Policy

**Last updated: November 17, 2026**

Riffora is a Discord music bot and private web dashboard maintained by Meher Sarana Papineni. This policy describes information processed when you use the bot or dashboard.

## Information Riffora processes

- **Discord sign-in:** Discord user ID, username, display name, and avatar returned through the `identify` scope.
- **Server access checks:** Server IDs, names, icons, ownership status, and permission values returned through the `guilds` scope. Riffora uses these to show servers you can manage and where the bot is present. It does not request a list of server members for the dashboard.
- **OAuth session:** Discord provides an access token so the backend can retrieve the profile and server information above. Riffora keeps that token and the dashboard session in backend memory, not in browser storage or a database. The session expires after 12 hours by default (the deployment can configure this). Signing out revokes the token. Restarting the backend ends active sessions.
- **Music playback:** Search text, track details, and the active player queue are processed in backend memory to provide playback. They are not saved to a database by the current version. Searches and playback requests are sent to Discord and YouTube or the relevant music source as needed to provide the service.
- **Browser storage:** The dashboard saves the selected server ID and a short recently played list (track title, URL, thumbnail, duration, and uploader) in your browser's local storage. This remains on that browser until you clear the site's stored data. It is not synchronized to Riffora's backend.
- **Operational logs:** The backend may log server IDs and diagnostic information when an error occurs. Hosting providers may retain service logs according to their own policies and settings.

## How information is used and shared

Riffora uses this information to authenticate the dashboard owner, check server-management permissions, display player state, search for tracks, and control playback. Information is sent to Discord's API for sign-in and server permission checks, and to YouTube or the selected music source for search and playback. If Riffora is hosted by a third-party provider, that provider processes service traffic and operational logs to run the application.

Riffora does not sell personal information. It does not use Discord data for advertising or for purposes unrelated to the bot and dashboard features described here.

## Retention and deletion

Backend sessions, OAuth tokens, server permission details, player state, and queues are held in memory while needed and are cleared when their session expires, the user signs out (for the token/session), or the backend restarts. The configured session lifetime may differ from the 12-hour default. Discord controls the lifetime of its OAuth tokens; signing out asks Discord to revoke the current token.

Browser history and the selected server are stored locally in your browser. Clear the site's local storage or site data in your browser to remove them. You can also revoke Riffora's Discord authorization in Discord's **Authorized Apps** settings.

To ask a question or request help with a privacy request, contact **[add a support email before publishing]**. Do not include passwords, access tokens, or other secrets in a request.

## Security and changes

Riffora uses server-side sessions and HttpOnly cookies. The secure-cookie setting should be enabled when the dashboard is served over HTTPS. No online service can guarantee absolute security. This policy may be updated when the app's data practices change; the update date above will be revised.

