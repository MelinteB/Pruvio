"""Source-level UI regression checks for responsive Core/Business rollout.

CI also runs real Core React component tests/build and Business production bundle.
Actual touch-device and visual viewport QA remain manual release gates.
"""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def read(relative):
    return (ROOT/relative).read_text(encoding='utf-8')

def test_core_brand_is_unique_and_marketing_banners_removed():
    main=read('frontend/src/main.jsx')
    hero=read('frontend/src/professional/BrandExperience.jsx')
    promos=read('frontend/src/PromotionsPreview.jsx')
    assert "import './core-v7161-responsive.css'" in main
    assert main.count('srcSet="/static/pruvs-logo-compact.webp"')==1
    assert 'core-v7160-sidebar-logo' not in main
    assert 'core-v7160-sidebar-feature' not in main
    assert 'BrandPhrase route=' not in main
    assert 'core-v7160-brand-line' not in hero
    assert 'core-v7160-floating-mark' not in hero
    assert 'core-v7160-bottom-guide' not in hero
    assert 'Offers from participating businesses' not in promos
    assert "request('/loyalty/promotions')" in promos
    assert '<CampaignCarousel campaigns={items}' in promos

def test_home_has_actions_first_and_optional_offers_after():
    main=read('frontend/src/main.jsx')
    history=read('frontend/src/Receipts.jsx')
    assert '<History home>{PRUVS_REWARDS_UI_ENABLED&&<PromotionsPreview/>}</History>' in main
    assert 'export function History({home=false,billsOnly=false,children=null})' in history
    assert history.index('{home&&<HomeWelcome user={user}/>}')<history.index('{home&&children}')
    assert '{!home&&<Title eyebrow="YOUR BILL LIBRARY"' in history
    assert '!home&&<small className="muted">' in history

def test_core_tablet_phone_and_small_phone_modes():
    code=read('frontend/src/main.jsx')
    css=read('frontend/src/core-v7161-responsive.css')
    for bp in ('@media(max-width:1024px)','@media(max-width:640px)',
               '@media(max-width:375px)'):
        assert bp in css
    assert '.core-experience.with-sidebar .content' in css
    assert 'margin:68px auto 0!important' in css
    assert 'display:none!important' in css
    assert 'grid-template-columns:repeat(5,minmax(0,1fr))' in css
    assert 'core-v7161-scan-tab' in code
    assert 'core-v7161-more-tab' in code
    assert 'role="dialog"' in code
    assert 'aria-modal="true"' in code
    assert 'More navigation' in code
    assert "event.key === 'Escape'" in code
    for route in ('/history','/inbox','/expenses','/account','/subscription','/support'):
        assert route in code
    assert 'env(safe-area-inset-bottom)' in css

def test_business_mobile_drawer_covers_tablet_and_campaign_studio():
    main=read('business_frontend/src/main.jsx')
    css=read('business_frontend/src/business-v0616-responsive.css')
    assert "import './business-v0616-responsive.css'" in main
    assert 'pruvs-business-compact-brand' in main
    assert 'pruvs-business-mobile-login-brand' in main
    assert '@media(max-width:1024px)' in css
    assert '@media(max-width:700px)' in css
    assert '@media(max-width:420px)' in css
    assert '.pruvs-business-2027 .sidebar.show' in css
    assert 'pruvs-business-nav-scrim' in main
    assert 'overflow-x:auto' in css
    assert '.pruvs-campaign-library-filters' in css
    assert '.pruvs-studio-2027-workspace' in css
    assert 'grid-template-columns:minmax(0,1fr)' in css
    assert 'min-height:44px' in css
    assert 'aria-expanded={menu}' in main

def test_location_aware_loyalty_release_guards_and_navigation():
    core=read('app/react_app/loyalty_v06.py')
    business=read('business/pilot_v06.py')
    api=read('business/main.py')
    rewards=read('frontend/src/Rewards.jsx')
    merchant=read('business_frontend/src/main.jsx')
    location=read('business_frontend/src/LocationManager.jsx')
    css=read('frontend/src/core-v7161-responsive.css')
    assert "PRUVS_LOCATION_TEST_MODE" in core
    assert "body['location']=location" in core
    assert 'PRUVS_RECEIPT_LOCATION_CHECK_ENABLED' in business
    assert 'PRUVS_RECEIPT_LOCATION_RADIUS_METERS' in business
    assert "@app.put('/v1/merchant/stores/{store_id}')" in api
    assert 'Pause or archive active loyalty programs' in api
    assert "['Loyalty operations'" in merchant
    assert "method:'PUT'" in location
    assert 'Search area on map' in rewards
    assert 'pruvs-v7166-map-offers' in rewards
    assert '.core-experience .brand-membership .membership-plan-badge{' in css
    badge=css[css.index('.core-experience .brand-membership .membership-plan-badge{'):][:260]
    assert 'display:inline-flex' in badge
    assert 'display:none' not in badge

def test_loyalty_programs_are_grouped_under_locations_in_an_accessible_tree():
    manager=read('business_frontend/src/ProgramManager.jsx')
    css=read('business_frontend/src/style.css')
    assert 'pruvs-program-tree' in manager
    assert '<details className="pruvs-program-branch"' in manager
    assert '<summary>' in manager
    assert 'p.store_id===store.id' in manager
    assert 'No loyalty programs linked to this location.' in manager
    assert 'pruvs-program-orphan' in manager
    assert '@media(max-width:650px)' in css
    assert '@media(prefers-reduced-motion:reduce)' in css

def test_release_metadata_matches_across_bundles():
    assert 'RELEASE = "7.1.66"' in read('app/reliability.py')
    assert "version:'7.1.66'" in read('frontend/scripts/stamp-build.mjs')
    assert "pruvs-shell-v7.1.66" in read('app/static/react-service-worker.js')
    assert "CLIENT_RELEASE = '7.1.66'" in read('frontend/src/professional/ReleaseUpdateBanner.jsx')
    assert "version='0.6.22'" in read('business/main.py')
    assert 'Pruvs Business · v0.6.22' in read('business_frontend/src/main.jsx')
