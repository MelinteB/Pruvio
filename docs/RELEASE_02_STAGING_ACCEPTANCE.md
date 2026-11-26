# Core 7.1.71 / Business 0.6.24 — staging acceptance (#48)

Target: combined application, not the suspended standalone services. No production deployment.
Do not close issue #48 based on a build or CI alone.

## Additive Business schema prerequisites
1. Identify the actual staging Business database (do not assume the Render instance name indicates isolation).
2. Take and verify a recoverable staging backup.
3. Execute b14a0624_campaign_gallery.sql and b15a0624_management.sql using an authorized staging database writer.
4. Verify all three new tables exist and original row counts are unchanged. No migrations are executed by an HTTP request.
5. Application rollback: redeploy previous tested commit; keep additive tables and their data. Do not drop tables as part of routine rollback.

## Live merchant + customer journey
- Confirm original account can sign in; check owner vs analyst permissions.
- Create/edit/duplicate location, search and Google listing, verify hours and manual fallback.
- Publish a program at an active location. Check locked criteria vs metadata-only editing.
- Request approval. Verify pending state, platform-admin decision, denial/revoke behavior.
- Validate all readiness flags/schema. No automatic approval.
- Save a gallery of 1–5 merchant-owned photos; reorder and change cover, edit draft, generate AI copy using all images, publish.
- Compare actual Core Home and Wallet cards with Business preview; verify no repeated numerical terms, manual gallery navigation and desktop/mobile layouts.
- Submit consented qualifying receipts using an authorized staging customer; review each code and approve a complete package; redeem reward; rejoin only when eligible.
- Unpublish/republish; ensure revoked or unready merchant is not advertised while existing wallet records stay readable.
- Pause and attempt retirement with customer progress, claims or rewards; verify refusal without deleting any history.
- Verify EN/RO and PWA, previous identity security release tests, exact Render build checks.
- Record acceptance results separately, including actual versions and database identity.

## Known limitations requiring further engineering/acceptance
- Current media pipeline uses public R2 assets with opaque URLs; draft records are not advertised, but strict private draft object access and orphan cleanup still need work.
- Old rendered artwork can contain baked headline text; regenerate from original source manually. No destructive bulk media rewrite.
- Gallery mode is manual image browsing, separate from existing single-photo GIF/MP4; multi-photo video montage is not implemented.
- Numeric text guard detects common explicit counts/currencies, not every semantic contradiction or numbers spelled out in marketing language.
- Legacy non-receipt demo mode is preserved; full staged readiness and authorized merchant approval must be confirmed before actual receipt acquisition.
- Full original Release 02 onboarding/notifications and wider bilingual UI audit, completed Release 01 acceptance, and real authenticated receipt-to-reward acceptance are outstanding.
