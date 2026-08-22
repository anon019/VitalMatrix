# 2026-08-22 Public Repo Sync Log

## Scope

This sync updates the public `VitalMatrix` repository from the server-side working source while keeping the independently maintained WeChat mini program unchanged.

## Included

- Vertex AI Gemini 3.7 migration and structured nutrition analysis
- Split nutrition core analysis and future-meal recommendation pipeline
- Oura and Polar data coverage, resilience, and schema updates
- Private signed nutrition media delivery and permanent meal-photo retention
- Web nutrition, AI, dashboard, and trend updates
- Nutrition poster V9 with deterministic text and verified nutrition layout
- Exportable system architecture and nutrition-poster workflow diagrams
- GitHub-renderable SVG previews embedded directly in README and architecture docs
- Complete 1600px PNG exports with Chinese labels, summary cards, and corrected text fit
- Database migrations, regression tests, and public documentation

## Explicitly Excluded

- All changes under `miniprogram/`; the authoritative mini program source remains on the Mac development environment
- Runtime `.env` files, uploaded meal photos, generated posters, backups, local caches, and virtual environments
- Server-specific domains, absolute paths, certificates, alert scripts, and deployment credentials

## Public-Safety Adjustments

- Kept OAuth callbacks, CORS origins, and OpenRouter request identity environment-driven or templated
- Kept upload storage paths relative to the backend source tree
- Preserved the reusable Nginx template and removed direct public exposure of nutrition uploads
- Preserved the public repository name and GitHub no-reply commit identity

## Validation

- Backend targeted regression suite: 31 passed
- Web clean dependency install and production build: passed
- Secret, private-domain, absolute-path, private-asset, and miniprogram-diff scans: passed
- Diagram HTML structure, pinned CDN versions, and SRI attributes: passed
