# Mini Program

## Version

- Current version: `0.3.15`
- Change history: `CHANGELOG.md`
- Release notes: `docs/releases/2026-09-06-v0.3.15.md`

## Scope

This repository contains the WeChat mini program only.

- daily dashboard
- trends view
- AI recommendations
- nutrition capture and analysis
- settings and sync utilities

## Architecture Diagrams

- [Mini program frontend architecture](docs/diagrams/miniprogram-frontend-architecture.html)
- [Nutrition analysis, asynchronous recommendations, and poster flow](docs/diagrams/nutrition-analysis-poster-flow.html)

## Local Development

1. Open the current directory in WeChat DevTools.
2. Keep `project.config.json` for local-only development.
3. Use `project.config.json.example` when you need a shareable config template.
4. Never commit `project.private.config.json`, `.claude/`, or any personal IDE config.

## Recent Updates In 0.3.15

- deduplicate concurrent requests, prevent stale cache writes, and append only unique new meal rows
- preserve existing content on failed refresh, with a visible retry action
- reduce AI view payloads and repeated normalization
- read meal scores, identified foods, and future menus from `ai_analysis`
- bypass meal list/detail caches, prepend uploaded records, and migrate local business caches once
- read image-analysis model metadata from `current_ai_model`; retain signed image URLs

## Previous Updates In 0.3.13

- replace the nutrition trend number strip with five truthful seven-day small-multiple bar charts
- keep daily values visible above each bar, label weekdays and dates directly, and mark missing days as `--`
- show recorded-day averages separately, align all seven days to a stable per-metric scale, and omit decorative full-height gray tracks
- render all health-insight items directly with no truncation or expand/collapse interaction
- keep list and detail view models compact so full AI payloads are not repeatedly serialized through `setData`
- use `/api/v1/auth/miniprogram-login` for silent fixed-user WeChat authentication with no password, login page, or logout workflow
- migrate legacy empty-user tokens and known business caches through auth storage v2 without clearing pending local image drafts
- serialize concurrent login and 401 refresh work, replay each business request at most once, and show an explicit retry state instead of an endless skeleton

## Previous Updates In 0.3.12

- format nutrition upload `meal_time` as local `YYYY-MM-DD HH:mm`, matching the backend multipart contract
- keep the selected meal time in the device timezone instead of converting it to UTC with `toISOString()`
- centralize upload date-time formatting in the shared date utility and retain the existing single-upload guard
- distinguish future breakfast, lunch, dinner, and snack recommendations with meal-specific symbols, muted tints, and active states, including English backend enum values
- keep recorded calorie and macro intake visible for partial days, with semantic color fills and explicit reference-progress percentages

## Previous Updates In 0.3.11

- keep the poster-generation entry disabled until the future-three-meal recommendation reaches `completed`
- refresh the short-lived signed poster URL through the ordinary cached-poster endpoint whenever the preview is reopened or a displayed URL fails
- remount the poster image when `content_digest` changes, retain the 3:4 natural-ratio `widthFix` presentation, and reserve a safe-area action footer
- save the original `poster_url` without Canvas processing, keep verified metrics accessibility-only, and expose `layout_version` for online-version diagnosis
- preserve backend messages for poster HTTP 422, 429, and 502 responses instead of rewriting every error as a quota failure

## Previous Updates In 0.3.10

- restore high-contrast deep-green headers on the AI and settings pages after a partial CSS override made dark text disappear against dark backgrounds
- refine nutrition-rating labels into consistently aligned status capsules with semantic color, inset highlight, and no displaced external shadow
- replace the settings goal placeholder with the server-backed `health_goal` and `training_plan`, including a real edit-and-save flow used by AI and nutrition analysis
- normalize the settings tab icon's optical size to the other four navigation icons while preserving the existing icon style
- reintroduce friendly nutrition, recovery, activity, and knowledge symbols inside the cleaner AI recommendation hierarchy

## Previous Updates In 0.3.9

- disable page-level `requiredComponents` lazy loading after confirming the current WeChat DevTools could mount static page frames without creating Page instances
- restore real dashboard, trends, nutrition, AI, and settings data rendering after developer-tool login recovery
- verify the dashboard and nutrition pages against live API responses in WeChat DevTools instead of relying only on static checks

## Previous Updates In 0.3.8

- bypass the shared GET cache entirely for recommendation-status polling and explicitly force the final meal-detail refresh
- align the pending and failed recommendation states with the two-stage backend flow, including recommendation-only retry
- preserve and render all future-meal timing, flavor, experience, portion, protein, ingredient, and cooking-step fields
- present every recommended dish as an independent recipe card and keep flavor notes and menu rationale at the meal-card footer
- standardize failed detail images on the `imageLoadFailed` state while retaining the session-level missing-media circuit breaker

## Previous Updates In 0.3.7

- start recommendation-status polling two seconds after upload recognition completes, then force-refresh the meal detail when recommendations finish
- render recipe ingredients as wrapping tags and cooking instructions as individually numbered steps instead of concatenated paragraphs
- replace failed historical meal images with a stable “历史图片不可用” state and stop automatic 404 refresh loops

## Previous Updates In 0.3.6

- redesign the nutrition-detail hierarchy around one compact meal overview, clearer analysis sections, and a calmer future-24-hour recommendation flow
- replace the repeated missing-recipe placeholders with one honest backend-availability note, while keeping all returned portions and nutrients visible
- collapse failed meal photos into a compact fallback instead of leaving a large blank hero, and retain a single signed-media refresh attempt
- refine the dashboard, trends, nutrition capture, AI guidance, and settings surfaces with consistent section rhythm, press feedback, consumer-facing copy, and softer data cards
- remove model and backend URL details from consumer UI while preserving all underlying API adaptations

## Previous Updates In 0.3.5

- make future-meal tabs show concise breakfast, lunch, and dinner labels instead of squeezing full menu names into three narrow columns
- keep the complete menu title in the selected meal card and expose backend-provided portion and protein values for each dish
- hide empty ingredient, cooking-step, and health-benefit rows while clearly identifying recipe details that the backend did not provide
- support additional compatible ingredient and cooking-step aliases when future backend responses include them

## Previous Updates In 0.3.4

- restore nutrition, training, sleep, activity, and recovery trends to one continuously scrollable page
- add a non-exclusive trend index that jumps to each section without hiding or unloading the others
- restore the nutrition page's Natural Table visual language, meal emojis, organic background, steam loading animation, and colorful nutrition accents
- retain the v0.3.3 two-stage upload, recommendation polling, timeout recovery, and duplicate-submission protection
- keep nutrition trend metrics full-width while restoring the richer surrounding trend presentation

## Previous Updates In 0.3.3

- show meal recognition and core nutrition results as soon as upload returns, without waiting for future-diet recommendations
- poll recommendation status independently every two seconds, stop after 90 seconds, and clean up on page hide or unload
- retry only the recommendation endpoint after recommendation failure; image upload and recognition are never repeated
- recover ambiguous client upload timeouts by refreshing recent meals before asking the user to try again
- remove user-confirmation questions while retaining confidence, portion assumptions, and uncertainty notes
- support current and legacy recommendation shapes without treating temporarily empty recipe arrays as meal failures

## Previous Updates In 0.3.2

- unified all six pages around the established green health-product palette and a calmer data-first hierarchy
- changed nutrition trends from two cards per row to one full-width metric per row
- added trend-category switching so only the active group is rendered, with heart-rate detail deferred until sleep is opened
- redesigned AI recommendations without the purple starfield, glow effects, or continuous decorative animation
- simplified nutrition capture, nutrition detail, and settings into consistent white surfaces with restrained green accents
- fixed the settings page remaining blank when login restoration completed after initial page creation

## Previous Updates In 0.3.1

- display every backend-provided follow-up meal instead of truncating the list to one recipe
- add a compact meal switcher so lunch, dinner, snack, or next-day meals remain easy to scan
- remove model names, legacy-analysis labels, and upgrade controls from consumer nutrition screens
- turn the top-level analysis conclusion into a concise meal brief with the full analysis below
- support additional dish calorie and content field aliases without rendering misleading `0 kcal` values
- simplify poster status copy while retaining backend-verified nutrition metrics and full scrolling

## Previous Updates In 0.3.0

- switched mini program authentication to `/api/v1/auth/wechat-login`
- preserved signed nutrition-media query strings and added bounded expired-link recovery
- added dashboard nutrition priority cards, metric-specific source dates, and minute-based sedentary display
- added five nutrition trend series with averages calculated only from recorded days
- exposed the backend model, stale-source date, prompt version, and data completeness in AI guidance
- adapted user profile reads and updates to `/api/v1/user/profile`
- exposed profile and device settings through the main tab bar
- moved nutrition posters to the on-demand backend generation flow
- added full-height poster preview, safe-area actions, complete-image saving, and retry states
- prioritized calorie ranges, confidence, confirmation questions, and concise health insights
- switched next-meal content to `next_meal_recipes` and reduced it to one focused menu
- reorganized AI recommendations into nutrition, recovery, activity, and health knowledge
