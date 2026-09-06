# Codex migration performance and code review

## Scope and fixes

Reviewed the Codex subprocess adapter, image preprocessing, nutrition persistence and background recommendations, poster generation, client field mappings, polling, and public deployment configuration.

- High: cancelling an outer request deadline previously left the CLI process running. Each run now starts an isolated process group; cancellation and timeout terminate and reap it, including tool descendants.
- High: semaphore wait was outside the timeout. Queue admission and execution now share one deadline, so queued requests cannot start after their budget has expired.
- High: default core retries (260 seconds), text (180 seconds), and posters (600 seconds) exceeded Web/proxy timeouts. Defaults are now core 60 seconds per attempt / 130 seconds total, text 130 seconds, poster 110 seconds including CLI queueing. Background recommendation budget remains 180 seconds. Existing environment overrides must be reviewed; transport budgets must allow additional preprocessing, cleanup and transfer time. These are failure bounds, not promised generation latency.
- Medium: recommendation lock lifetime equalled model execution timeout and excluded queueing. With bounded queueing it now includes a 60-second margin for database work and cleanup.
- Medium: poster digest locks accumulated indefinitely. Weak references now release unused locks while preserving mutual exclusion for active holders and waiters.
- High: Web and the public miniprogram source read an obsolete analysis field. Both consume `ai_analysis`; miniprogram list ratings and detail data now match the backend response.
- Medium: a completed status followed by a failed detail request stopped polling permanently. Both clients now retain the pending state until detail data is fetched successfully.
- Medium: deployment checks hardcoded a server path and account home. Paths now derive from the script directory and configurable environment values; Codex authentication respects its configured home.
- Configuration: concurrency must be positive and bounded; timeout values must be positive. Documented Python minimum is 3.11 because the implementation uses `asyncio.timeout`.

## Verification

- Backend: `python -m pytest tests -q`, 49 passed locally and in the sanitized public checkout; two existing python-jose datetime deprecation warnings.
- Subprocess regression tests run actual child processes for timeout and cancellation, plus semaphore queue expiration.
- Web: ESLint and TypeScript/Vite production build passed.
- Public miniprogram: `node --test miniprogram/tests/nutrition-contract.test.cjs`, three passed; list JavaScript syntax check passed.
- Public checkout: selected source files only; domain/path and credential-pattern checks before push. Local environment, media, private configuration and local diagrams excluded. Existing public domain references templated.

## Boundaries

No new paid AI benchmark was run; this review improves cleanup and bounded waiting rather than claiming a measured inference speedup. Browser visual verification and WeChat device verification were not performed. Public miniprogram changes must be merged into the authoritative Mac project and packaged through the WeChat release workflow. A GitHub push does not update an installed miniprogram.

This was a focused review of the changed workflow, not an exhaustive repository security audit. Codex credentials and sandbox availability must be configured for the service account. Poster generation remains synchronous and can time out under slow upstream service; persistent asynchronous poster jobs would require a separate API/client contract change.
