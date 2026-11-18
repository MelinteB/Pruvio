# Pruvs 2027 — design architecture, audit and staged release roadmap
**Status:** draft product plan, prepared 2026-11-18. **Not** a certificate of production readiness.
**Scope:** Pruvs Core (consumer) and Pruvs Business (merchant); combined staging deployment,
independent API contracts and independently numbered releases.
**Starting point:** Core 7.1.59, Business 0.6.14.

## Evidence and design principles
2027 has not happened. Recommendations are projections anchored in published 2025–2026
platform guidance, not established 2027 facts:

- Google Material 3 Expressive research: personalization, clearer emphasis, purposeful
  shape and motion (https://design.google/library/expressive-material-design-google-research).
- Apple Human Interface Guidelines: hierarchy, adaptable materials, reduction of
  transparency/motion and strong contrast
  (https://developer.apple.com/design/human-interface-guidelines/materials).
- Nielsen Norman Group State of UX 2026: trust in AI interfaces depends on
  transparency, control, consistency and failure handling
  (https://www.nngroup.com/articles/state-of-ux-2026/).
- WCAG 2.2: focus visibility, accessible authentication, touch target sizing and
  other success criteria (https://www.w3.org/TR/WCAG22/).
- Core Web Vitals: user-facing LCP, INP and CLS
  (https://web.dev/articles/vitals).
- EU European Accessibility Act: may apply to covered services such as e-commerce
  and banking; confirm applicability, exemptions and implementation with counsel.
  (https://commission.europa.eu/strategy-and-policy/policies/justice-and-fundamental-rights/disability/european-accessibility-act-eaa_en).

**Selected aesthetic:** warm paper canvas, ink-green typography, deep forest/teal
actions, authentic food/product imagery, 16–26px radius family, unobtrusive depth,
expressive but restrained motion, responsive density and meaningful interaction states.
**Deliberately not selected:** generic full-page glassmorphism, perpetual decorative
animation, ungrounded AI suggestions, tiny icon-only actions, misleading fake payment
confirmations, and hidden promotion approval.

## Current source audit (2026-11-18)
Findings from the staging source code, not a live, device-lab usability study:
- Business shell inherited a large single-file stylesheet and several feature-specific
  layers, leading to inconsistent card, field, button and spacing values.
- Core already had a more complete consumer/navigation architecture but layered many
  older visual refresh files with contrasting blue and green palettes.
- Campaign Studio used an approximation of the customer creative rather than the
  actual Core campaign card styles. Uploaded media, copy review and promotional
  rule validation must remain one coherent creation workflow.
- Staging and pilot copy appeared in old merchant sign-in UI and the example email
  was prefilled. These should not be shipped in production.
- Business frontend package includes build but no dedicated automated component
  test runner; Core already runs Vitest. Business needs true role and workflow E2E tests.
- No real-device WCAG, Safari/iOS, Android, 320px or field Web Vitals measurements
  have been collected in this exercise. Do not claim certification.
- Backend billing, settlement, wallet, per-user state and receipt storage require
  their own E2E and security gates; a new visual layer does not certify them.

## First foundation candidate in this branch
- Shared tokens: `backend/shared_ui/pruvs-2027-tokens.css`.
- Shared customer creative: `backend/shared_ui/pruvs-campaign-card-2027.css`.
- Core redesign layer: `backend/frontend/src/core-2027.css`.
- Business responsive shell/login layer: `backend/business_frontend/src/business-2027.css`.
- Merchant AI creative workspace: `backend/business_frontend/src/studio-2027.css`.
- Business WYSIWYG: `backend/business_frontend/src/CorePromotionPreview.jsx`.
  It imports the real Core campaign-creative and promotions CSS along with the
  shared card rules; the preview CTA is deliberately non-interactive and draft-only.
- Reduced-motion customer video controls, real merchant sign-in (no example email),
  keyboard mobile drawer and media preview loading/failed states.
- Existing AI/image controls, merchant approval and program reward terms preserved.
- No database migration and no production change in this foundation candidate.

## Recommended 6-increment plan plus one production release gate
These numbers are **planning targets**, not automatic release promises. Core and Business
must continue to ship independently with backward-compatible API contracts. If a
workstream passes earlier it can ship on its own. Database changes remain additive.

| Gate | Business target | Core target | Main outcome | Must-pass evidence |
|---|---|---|---|---|
| 1: Foundation | 0.6.15 | 7.1.60 | Unified tokens, modern shell, Core-matched Campaign Studio preview | Both builds pass; draft approval, static/GIF/MP4, mobile card verification |
| 2: Transaction journeys | 0.6.16 | 7.1.61 | Seamless scan, split, next step, payment and reward navigation | Two-user bill, currency, owner settlement, data isolation; no false transfer claims |
| 3: Merchant operations | 0.6.17 | 7.1.62 | Campaign library, editing, scheduling, receipt review, reports and admin consistency | Role-based access, draft/paused/published lifecycle, merchant/customer data boundaries |
| 4: Accessibility & devices | 0.6.18 | 7.1.63 | WCAG 2.2 AA targeted, touch/keyboard/screen-reader audit, responsive forms; optional dark mode after review | Manual + automated keyboard/contrast checks; phones 320–430px, tablets and desktop |
| 5: Performance & resilience | 0.6.19 | 7.1.64 | Caching, media optimization, offline/empty/error states, E2E automation and observability | Field Web Vitals p75 LCP <=2.5s, INP <=200ms, CLS <=0.1; security/recovery checks |
| 6: Product hardening | 0.6.20 | 7.1.65 | Multi-merchant beta, copy/legal review, audit trail, support, subscription and release controls | Merchant UAT sign-off, migration backup/rollback rehearsal, no unresolved critical defects |
| Final promotion decision | independent production release | independent production release | Ship approved components to production, with separate rollout switches | Formal go/no-go, backup, migration plan, monitoring and rollback owner |

**Estimate:** six disciplined staging iterations per product **plus one production
promotion gate**. Actual count can increase if tests uncover critical defects; no
specific number of builds guarantees a professional product.

## Cross-device acceptance matrix
Test at 320/360/375/390/430/768/1024/1440px, including real iOS Safari,
Android Chrome and desktop Chrome/Firefox/Safari where available.
For every screen verify:
- No horizontal overflow, cramped controls or obscured content.
- Navigation: focus order, skip link, Escape for menus/dialogs, clear active tab.
- All input validation errors, disabled states and confirmation actions.
- Text 200% zoom, high contrast, reduced motion, larger OS font.
- Authenticated role separation: Core account A/B, Business owner/manager/admin,
  and rejected cross-tenant requests.
- Payment state never implies a bank-confirmed transfer if only self-reported.
- Photo upload, AI copy from the real uploaded image, generated GIF/MP4, public
  CDN read, and displayed Core card with matching text and merchant-owned URL.
- Approved program terms never altered by a generated creative; publisher consent.
- Unavailable API/storage, timeouts, expired sessions, stale caches and reloads.

## Performance & production requirements
Track field LCP <=2.5s, INP <=200ms and CLS <=0.1 at 75th percentile, split
mobile/desktop. Define build-size budgets after measuring the baseline, rather than
inventing a current score. Add accessible Business component/E2E tests (e.g. Playwright),
visual snapshots for the shared Core card at phone/tablet/desktop and cross-browser QA.
Measure images and video, avoid autoloading heavy creatives outside the viewport.

**Release protection:** keep combined staging and production main separate; require
GitHub passing checks, explicit Render deployment, independent Core/Business versions,
contract-compatible DB migrations, backups and an owner-approved rollback process.
Avoid `git add .`; stage exact files only. Never copy staging secrets to production.

## Go/no-go
**No-go until:** no critical security/payment/account-isolation defects; verified
retention/privacy and merchant permission model; working R2 media pipeline including
fallbacks; E2E bill/payment/rewards and merchant campaign flows; acceptable device
accessibility results; real-user usability acceptance; monitoring and rollback tested.

## Limitations of this audit
The repository was inspected and CI can validate Python, React and build contracts.
No authorized user login, production screenshot comparison, actual mobile device lab,
real merchant testing, formal penetration test or payment-provider acceptance was
conducted here. Those remain independent release gates.
