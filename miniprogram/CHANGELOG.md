# Changelog

All notable changes to this mini program will be documented in this file.

## [0.3.15] - 2026-09-06

### Performance
- Share cold concurrent GET requests and prevent invalidated responses from overwriting newer cache entries.
- Encode query cache keys, guard pagination against duplicate and stale responses, and serialize only appended rows.
- Normalize AI recommendations once and omit unused complete response objects from view state.

### Fixed
- Preserve the public client's polling retry after completed-status detail refresh failures and retain its contract tests.
- Preserve existing nutrition content after network failures, expose retry, and avoid marking failed refreshes as fresh.
- Refresh the displayed date on reentry and accept numeric nutrient strings.
- Read meal analysis and scores from `ai_analysis`, prioritizing nested nutrition and recommendations over obsolete top-level placeholders.
- Preserve all future-menu names, timing, calories, dishes, and menu rationale.
- Bypass meal list/detail caches and prepend uploaded records immediately.
- Clear known local business caches once on upgrade while preserving authentication and image drafts.
- Read image-analysis model metadata from `current_ai_model`; preserve response-driven poster/recommendation models and signed image URLs.

## [0.3.13] - 2026-08-25

### Changed
- Replace the nutrition trend's plain seven-day number row with one mobile-first bar-chart card per metric for calories, protein, carbohydrates, fat, and recorded meals.
- Directly label every bar with its value, weekday, and date, while keeping the recorded-day average prominent in each card header.
- Reuse the nutrition palette for metric identity and give every metric a stable reference scale that expands only when real values exceed it, so all seven days remain comparable without peak-relative distortion.
- Render every health-insight item returned by the backend directly, without truncation, expand/collapse state, or an extra interaction.
- Reduce list and detail `setData` payloads by retaining only template-facing meal fields and one normalized recipe collection.
- Switch the personal mini program to silent WeChat authentication through `POST /api/v1/auth/miniprogram-login`, with no password or user-facing login flow.
- Store token, expiry, auth mode, and login time atomically in an auth-storage v2 session and gate all business requests on that session.
- Remove the user-facing logout action; API tokens remain an internal transport detail rather than a product login flow.

### Fixed
- Render missing nutrition days as explicit `--` states instead of making a sparse series look like a complete numeric trend.
- Remove full-height gray nutrition bar tracks so bar height represents the value itself rather than progress inside a decorative background.
- Stop masking a failed settings-profile request with default values, and stop logging full health-response payloads in the developer console.
- Move inline Today-page style fallbacks into the existing normalized view model so the DevTools CSS analyzer no longer reports false syntax errors.
- Restore the nutrition trend empty state when the backend has no recorded values instead of always creating five empty metric cards.
- Migrate legacy empty-user tokens and known business caches once while preserving unrelated local state and pending image drafts.
- Deduplicate concurrent authentication and 401 refreshes globally, replay each failed business request at most once, and stop immediately for 403, 422, 429, 500, 502, and 503 responses.
- Replace indefinite authentication loading with a compact retry state across Today, Trends, Nutrition, AI, and Settings.

### Verified
- Check mixed, sparse, one-day, and empty seven-day nutrition payloads for stable-scale percentages, direct labels, and empty-state behavior.
- Check that three or more health strengths and weaknesses are all retained and that no insight toggle exists.
- Check JavaScript syntax, repository whitespace integrity, and confirm WeChat DevTools reports zero project-source problems after hot compilation.
- Confirm first launch makes one `wx.login` and one `/miniprogram-login`, concurrent callers share one authentication Promise, invalid codes are retried once, concurrent 401 responses share one refresh, and second 401/403 responses do not loop.

### Known validation limitation
- Final live-data and physical-device checks are recorded after the backend `miniprogram-login` deployment is available in WeChat DevTools.

## [0.3.12] - 2026-08-23

### Changed
- Give future breakfast, lunch, dinner, and snack tabs distinct symbols, muted tints, and active accents while retaining the existing nutrition-detail layout.
- Show explicit calorie, protein, carbohydrate, and fat reference percentages in the daily nutrition summary.

### Fixed
- Format nutrition upload `meal_time` as local `YYYY-MM-DD HH:mm`, matching the backend's strict multipart parser.
- Stop using `Date.prototype.toISOString()` for meal uploads so Singapore and other non-UTC device times are not shifted before submission.
- Centralize the upload date-time formatter in `utils/date.js` and use it for both explicit and default upload timestamps.
- Recognize English backend meal types such as `breakfast`, `lunch`, and `dinner` instead of falling back to the same apple symbol.
- Keep recorded-intake rings and bars rendered when `partial_day=true`; partial-day state now changes the explanation instead of hiding the visualization.

### Verified
- Check local date-time formatting, zero padding, multipart field mapping, JavaScript syntax, and repository whitespace integrity.
- Confirm the upload state machine still produces one guarded multipart request and does not retry automatically.
- Confirm in WeChat DevTools that partial-day intake renders colored 34%–46% progress and future meals render as breakfast `🌅`, lunch `☀️`, and dinner `🌙`.

## [0.3.11] - 2026-08-22

### Changed
- Gate poster generation on `recommendation_status=completed`, with an explicit prerequisite message while the future-three-meal plan is still pending or failed.
- Refresh short-lived signed poster URLs through the ordinary non-force poster endpoint whenever users reopen a poster or the displayed image URL fails.
- Use `content_digest` to remount updated poster pixels, record and display `layout_version`, and retain verified nutrition metrics only for the image accessibility label.
- Add a 3:4 loading placeholder while keeping the poster itself natural-width `mode="widthFix"`, vertically scrollable, and clear of the safe-area action footer.

### Fixed
- Preserve the backend's actual HTTP 422, 429, and 502 error messages instead of assuming every 429 response means the daily quota is exhausted.
- Save the original `poster_url` file without Canvas redraw, screenshot capture, fixed-pixel sizing, or secondary compression.
- Treat `generated=false` as a successful cached-poster response and replace the previous signed URL immediately after a confirmed force regeneration.

### Verified
- Check JavaScript syntax, WXML bindings, WXSS structure, poster state-machine behavior, and whitespace integrity.
- Confirm a real `generated=false` `nutrition-poster-v9` response opens without force generation, renders the complete 3:4 image, and keeps safe-area actions outside the poster.

## [0.3.10] - 2026-08-21

### Changed
- Restore a high-contrast, technology-oriented deep-green hero on the AI page and reintroduce friendly recommendation symbols without returning to the old purple starfield.
- Turn nutrition macro ratings into consistently aligned semantic capsules with fixed height, inset highlight, and a stable status dot.
- Read the settings health goal and training plan from the user profile, allow editing both values, and persist them through `PUT /api/v1/user/profile`.
- Scale the settings gear artwork inside its existing 81×81 canvas so its optical size matches the AI, nutrition, trend, and today icons.

### Fixed
- Prevent the AI title and settings title from rendering dark text on a deep-green background due to incomplete late-file CSS overrides.
- Remove the displaced label-background effect around “适中 / 充足 / 偏高” in nutrition analysis.
- Stop presenting a hard-coded “降脂降胆固醇” card as though it were the user's saved backend configuration.

### Verified
- Confirm the AI title, generation badge, summary, and recommendation cards render with readable contrast in WeChat DevTools.
- Confirm the settings page displays the live server health goal, exposes the edit state, and renders the corrected tab icon size.
- Confirm a live dinner detail renders aligned “适中 / 充足 / 偏高” capsules while preserving meal analysis and future meal data.

## [0.3.9] - 2026-08-21

### Fixed
- Disable `lazyCodeLoading: requiredComponents` after reproducing a WeChat DevTools state where tab shells rendered but page JavaScript never initialized and AppData contained no Page instances.
- Restore dashboard and all tab data rendering after the developer-tool account token expired and the simulator was reopened.

### Verified
- Confirm live dashboard values including readiness 81, sleep 6h13m, HRV 29ms, resting heart rate 59bpm, and three recorded meals.
- Confirm the trends page renders nutrition, training, sleep, activity, and recovery sections, and the nutrition page renders 1679 kcal, 87.2g protein, and recent meal records.

## [0.3.8] - 2026-08-21

### Changed
- Route recommendation-status requests directly through the uncached request layer and explicitly force-refresh meal details after completion.
- Preserve canonical `ingredients` and `cooking_steps` arrays alongside timing, flavor, experience, portion, and protein recipe fields.
- Present recommended dishes as independent bordered cards, with meal-level flavor, experience, and pairing rationale grouped at the footer.
- Align pending copy with “识图完成，饮食建议生成中” and expose “重新生成建议” as a recommendation-only failure action.

### Fixed
- Prevent the shared 10–30 minute GET cache or an older in-flight detail response from hiding newly completed recommendations.
- Standardize historical detail-image failure on `imageLoadFailed` and keep missing image URLs from being requested repeatedly during the app session.
- Confirm the active mini-program and server-poster request path contain no `recommendations.next_meals` reads; only `next_meal_recipes` is used for current detail content.

## [0.3.7] - 2026-08-21

### Changed
- Start recommendation-status polling on a strict two-second cadence after the upload response is handed to the meal detail page.
- Render recipe ingredients as wrapping tags and cooking instructions as separately numbered steps across string, array, and compatible object payloads.

### Fixed
- Wait for any in-flight detail request before forcing the final refresh when recommendation generation completes.
- Replace failed historical list thumbnails and detail photos with a stable “历史图片不可用” fallback without automatically re-requesting missing media.

## [0.3.6] - 2026-08-21

### Changed
- Rebuild the nutrition-detail hierarchy around a single meal overview, compact score presentation, explicit analysis sections, and a clearer future-24-hour recommendation flow.
- Turn future dishes into a numbered menu list with portions and nutrients, and show missing backend recipe details once per meal instead of repeating empty rows.
- Add page-specific visual refinement to the dashboard, trends, nutrition capture, AI guidance, and settings pages without changing their backend data contracts.
- Replace technical AI model and backend URL labels with consumer-facing generation time and service status copy.

### Fixed
- Collapse an unavailable meal photo into a compact explanatory fallback after one refresh attempt instead of preserving a large blank hero.
- Normalize next-day meal labels to stable breakfast, lunch, dinner, and snack tabs while retaining complete menu titles in the content area.
- Add consistent pressed states, safer action hierarchy, long-page navigation rhythm, and clearer empty or unavailable-content treatment across the mini program.

## [0.3.5] - 2026-08-21

### Changed
- Replace full-menu titles in the three-column recommendation switcher with concise meal-period labels and icons.
- Move each complete menu title into the selected recommendation card so it can wrap naturally without crowding the navigation.
- Display backend-provided portion and protein values for every recommended dish.

### Fixed
- Stop rendering empty ingredient, cooking-step, and health-benefit rows when those optional fields are absent.
- Show an explicit unavailable-detail state instead of blank labels, while accepting additional compatible recipe field aliases.

## [0.3.4] - 2026-08-21

### Changed
- Restore all nutrition, Polar training, Oura sleep, activity, and recovery trend groups to one continuous page instead of rendering only the selected category.
- Add a compact trend index for quick scrolling while keeping every trend group mounted and visible.
- Restore the nutrition page's warm Natural Table palette, organic background decoration, meal-time emojis, animated bowl loading state, colorful macro accents, and richer meal cards.
- Keep nutrition trend cards full-width for readability while restoring the surrounding visual hierarchy.

### Fixed
- Prevent users from mistaking hidden trend groups for removed movement, sleep, or nutrition data.
- Preserve the two-stage upload state, recommendation polling, timeout recovery, and upload deduplication while restoring the earlier nutrition UI.

## [0.3.3] - 2026-08-21

### Added
- Add independent two-second recommendation-status polling with a 90-second foreground limit and lifecycle cleanup on page hide or unload.
- Add recommendation-only retry and confirmed force-regeneration actions without re-uploading or re-analyzing the meal image.
- Add future-24-hour recipe timing, flavor profile, experience note, and menu rationale presentation.

### Changed
- End the blocking upload state as soon as the backend returns the meal's core recognition and nutrition analysis.
- Show pending, failed, and long-running recommendation states inside the recommendation card while keeping the completed meal analysis interactive.
- Replace confirmation questions with read-only confidence, portion-assumption, and uncertainty context.
- Replace the small-image timeout suggestion with a record-recovery flow that refreshes recent meals before showing a delayed-response message.

### Fixed
- Prevent duplicate multipart submissions during image selection, compression, upload, and ambiguous timeout recovery.
- Treat missing legacy analysis status as completed and safely normalize missing recommendation arrays without blanking the detail page.
- Preserve and display every identified food returned by the backend, including mushroom-and-pork and grilled-sausage items in the latest meal response.

## [0.3.2] - 2026-08-21

### Changed
- Unify the dashboard, trends, nutrition, AI, detail, and settings pages around the established green health-product palette with calmer surfaces and compact information hierarchy.
- Replace the trends page's all-at-once layout with category navigation and render only the active metric group.
- Display every nutrition trend metric as a full-width row with a seven-day series instead of a two-column card grid.
- Replace decorative starfields, glows, emoji-led controls, and nonessential continuous animations with restrained data-oriented labels and press feedback.
- Defer seven-day heart-rate-detail requests until the sleep trend is opened.

### Fixed
- Recover the settings page when login state becomes available after page initialization instead of leaving a permanent blank screen.
- Keep the nutrition detail, meal-plan switcher, poster preview, and backend-adapted fields intact while applying the new visual hierarchy.

## [0.3.1] - 2026-08-21

### Changed
- Show every backend-provided follow-up meal through a compact meal switcher instead of truncating `next_meal_recipes` to the first item.
- Replace model/version and legacy-upgrade UI with a concise meal brief and user-facing nutrition content.
- Simplify poster preview status text while preserving backend-verified calorie and macro values.

### Fixed
- Accept current and compatible dish calorie/content field aliases and hide unavailable dish calories instead of displaying `0 kcal`.
- Keep follow-up meal labels driven by the backend so dinner, snack, or next-day breakfast are represented accurately.
- Remove backend model labels from nutrition list cards and detail scores.

## [0.3.0] - 2026-08-21

### Added
- Add WeChat-code authentication through `POST /api/v1/auth/wechat-login`.
- Add dashboard nutrition priority cards, AI action entry, metric-specific Oura source dates, and five nutrition trend series.
- Add signed nutrition-media URL resolution with bounded refresh after an expired image or poster URL.
- Add editable profile fields for gender, birth month, and weight using the optimized profile API.
- Add on-demand backend poster generation, cached-result awareness, full poster preview, album saving, friend sharing, and confirmed force regeneration.
- Add calorie ranges, analysis confidence, user-confirmation questions, uncertainty notes, and progressive disclosure to nutrition details.
- Add AI recommendation regeneration with the backend-returned model and generation time.

### Changed
- Read all current and historical AI model labels from backend data; mark legacy meal analyses explicitly.
- Treat partial nutrition days as recorded intake, calculate weekly/trend averages only from recorded days, and interpret Oura activity durations as minutes.
- Show AI recommendation source date, stale state, prompt version, and data completeness without client-side date fallback.
- Use `GET/PUT /api/v1/user/profile` for user profile data.
- Prioritize `next_meal_recipes` and remove dependencies on `next_meals` and `next_meal_menu`.
- Reorder AI guidance into nutrition, sleep recovery, activity training, and health knowledge.
- Expose the existing settings page in the tab bar so profile fields are reachable.
- Keep the established online visual language while adding the new profile, nutrition, AI, and poster states.

### Fixed
- Send the required date range to `/api/v1/trends/overview` and exclude zero-meal dates from recorded-day averages.
- Replace missing historical meal thumbnails with a stable placeholder after one page-wide signed-URL refresh.
- Keep nutrition detail content visible when poster generation fails and provide an inline retry.
- Keep meal details on screen when loading fails instead of navigating away.
- Prevent duplicate poster generation and reserve `force=true` for the confirmed regenerate action.
- Download posters and verify their real dimensions before saving to the photo album.

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
