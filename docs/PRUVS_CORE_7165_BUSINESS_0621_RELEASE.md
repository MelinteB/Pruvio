# Pruvs Core 7.1.65 / Business 0.6.21

Prepared on 20 November 2026. This release is staged in Git only and must not be deployed until approved.

## Included changes

- Responsive campaign presentation with automatic rotation, progress timing, manual previous/next navigation and touch swiping.
- Campaign presentation pauses during hover, keyboard focus and touch interaction.
- Campaign creative preview identifies still images, animated GIFs and short MP4 videos.
- Picture-aware campaign watermark contrast and refined live-card watermark styling.
- Loyalty verification remains at campaign level instead of individual receipt level.
- Business checkout supports manual or scanned campaign codes and applies the campaign discount.
- Google Places failures now distinguish missing configuration, quota exhaustion, rejected server keys and rejected requests.
- Google diagnostic messages never expose API keys or upstream response bodies.

## Google Maps staging requirements

1. Finish and apply pending Render environment changes.
2. Set `PRUVS_GOOGLE_PLACES_API_KEY` for server-side Places API (New) requests.
3. Set `VITE_GOOGLE_MAPS_EMBED_KEY` for the Business frontend build when an embedded map is required.
4. Enable billing, Places API (New) and Maps Embed API in the relevant Google Cloud project.
5. Restrict the server key for its server-side use and the embed key by the staging web origin.
6. Redeploy after environment or build-time variable changes, then verify readiness and location search.

## Verification before deployment

- Core and Business production builds complete successfully.
- Core frontend test suite passes.
- Campaign, loyalty, Google Places and release metadata backend tests pass.
- Search for a real Romanian business and select the Google result.
- Save the location and confirm its name, address, latitude, longitude and place link.
- Confirm the embedded map or external directions link loads as configured.
- Confirm no secret value appears in the browser, API response or logs.

## Release control

Deploy only after explicit approval. The target is `Bogdan's Workspace / Pruvs-staging`.
