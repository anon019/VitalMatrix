# Changelog

All notable changes to this mini program will be documented in this file.

## [0.2.1] - 2026-03-25

### Fixed
- Prevent duplicate first-screen loads caused by `onLoad` and `onShow` both firing full data fetches.
- Add global re-login deduplication and auth-state cleanup for 401 responses.
- Replace UTC-based date generation with local-date helpers to avoid wrong-day requests near midnight.
- Stop automatic background refresh from showing success toasts on the index and AI pages.
- Fix nutrition summary meal counts to use backend summary fields instead of current-page list inference.
- Invalidate nutrition caches after upload and delete so the list and summary stay in sync.
- Avoid image error noise on nutrition detail pages when a meal has no photo.

### Improved
- Defer trends heart-rate recovery loading until after primary content is rendered.
- Add per-page in-flight load guards to reduce duplicate requests and redundant loading state changes.
- Clarify the Polar authorization entry so the UI does not imply an unsupported in-mini-program flow.

## [0.2.0] - 2026-03-05

### Added
- Request caching, layered loading, and performance-oriented page optimizations.
