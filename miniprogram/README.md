# Mini Program

## Version

- Current version: `0.2.1`
- Change history: `CHANGELOG.md`
- Release notes: `docs/releases/2026-03-25-v0.2.1.md`

## Scope

This directory contains the WeChat mini program for VitalMatrix, including:

- daily dashboard
- trends view
- AI recommendations
- nutrition capture and analysis
- settings and sync utilities

## Local Development

1. Open `miniprogram/` in WeChat DevTools.
2. Copy `project.config.json.example` to a local `project.config.json`.
3. Fill your own AppID locally via DevTools or the copied config file.
4. Update `utils/config.js` with your deployment domain.
5. If the backend enables `WEB_ACCESS_PASSWORD`, also set `SIMPLE_LOGIN_PASSWORD` in `utils/config.js`.
6. Do not commit `project.config.json`, `project.private.config.json`, or any local-only IDE config.

## Recent Updates In 0.2.1

- deduplicated page loading on first screen entry and page re-entry
- improved 401 re-login handling and request feedback throttling
- unified local-date generation to avoid wrong-day requests
- deferred trends heart-rate recovery loading off the primary render path
- fixed nutrition summary count and cache invalidation after upload/delete
- aligned settings copy with the currently supported Polar flow
