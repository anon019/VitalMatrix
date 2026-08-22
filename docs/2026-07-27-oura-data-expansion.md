# Oura V2 data expansion — 2026-07-27

## Outcome

The Health backend now persists the newly audited Oura collections and fields
instead of repeatedly reading them only from the remote API.

New persisted collections:

- Workout
- Enhanced Tag
- Rest Mode Period
- Continuous heart-rate samples

New normalized fields:

- Sleep heart-rate and HRV series
- 30-second and 5-minute sleep phases
- 30-second movement series
- Sleep battery/algorithm metadata
- Daily activity 5-minute class and MET series
- Activity MET-minute breakdown
- Oura source timestamps
- Pulse-wave velocity where the account/API permits it

The existing complete `raw_json` payloads remain retained.

## Database

Alembic revision: `c7a8d9e0f1b2`

New tables:

- `oura_workouts`
- `oura_enhanced_tags`
- `oura_rest_mode_periods`
- `oura_heart_rate_samples`

All event tables use per-user Oura IDs as idempotency keys. Heart-rate samples
use `(user_id, timestamp)`. Composite indexes support the main user/date and
user/timestamp query paths. Batch upserts are capped at 1,000 rows per SQL
statement.

The migration normalized the already retained sleep and activity JSON locally;
it did not redownload those historical payloads.

## Synchronization

Ongoing synchronization is now:

1. Oura signed webhook notification
2. background three-day reconciliation for the affected local user
3. daily 07:30/08:20 reconciliation
4. daily 20:30 end-of-day reconciliation

The former 15-minute Oura poll was removed. Polar's 15-minute poll is
unchanged.

Webhook endpoint:

`https://your-domain.example.com/api/v1/oura/webhook`

There are 20 active subscriptions: `create` and `update` for 10 supported data
types. POST events require Oura HMAC-SHA256 verification. The public GET
challenge uses a purpose-limited token derived from the application secret.

The sleep heart-rate detail API now reads the local continuous-heart-rate table
instead of making page-time Oura API calls.

## Capability isolation

Availability is cached per endpoint. A 401 from an optional/new endpoint no
longer marks the whole OAuth connection invalid or retries that endpoint every
sync cycle.

Available on 2026-07-27:

- Workout
- Enhanced Tag
- Rest Mode Period

Account/API access currently unavailable (401):

- Daily Resilience
- VO2 Max
- Daily Cardiovascular Age
- Ring Configuration
- Ring Battery Level

These are endpoint-level restrictions; the Oura authorization remains active.

## 2026 backfill result

Backfill was performed in bounded date windows with idempotent writes.

- Workouts: 228
  - walking: 224
  - running: 2
  - swimming: 1
  - HIIT: 1
- Enhanced tags: 6
- Rest-mode periods: 1
- Continuous heart-rate samples at final audit: 270,512
- Heart-rate duplicate timestamps: 0

The heart-rate total continues to grow through webhooks/reconciliation.

Normalized historical coverage:

- Sleep records: 505/505 heart-rate series, HRV series, movement series and
  algorithm versions; 451/505 have the 30-second sleep-phase series.
- Daily activity: 251/251 have 5-minute class data, MET series, source
  timestamp and MET-minute breakdown.

## Verification

- Full backend test suite: 16 passed
- Alembic current/head: `c7a8d9e0f1b2`
- No migration drift matches any table/column added by this change
- Public GET challenge: HTTP 200
- Public signed POST: HTTP 200, accepted
- Webhook subscriptions: 20 existing, 0 missing
- `health-backend.service`: active, `NRestarts=0`

Repository-wide `alembic check` still reports older unrelated drift: the
retained legacy `oura_daily_heart_rate` table, a historical AI index and
several old column comments. This change intentionally does not delete that
legacy table or rewrite unrelated migrations.

During setup, purpose-limited v1/v2 verification values appeared in local URL
access logs. Both versions were invalidated. Matching values were redacted
from the Health and Nginx logs without removing other log content. The current
v3 value has not been sent or logged.

## Maintenance scripts

- `backend/scripts/setup_oura_webhooks.py`
- `backend/scripts/backfill_oura_2026.py`

These scripts must run with the same runtime environment as
`health-backend.service`. Do not shell-source the systemd environment file and
do not print decrypted tokens.
