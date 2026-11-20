"""Regression checks for Campaign Studio smartphone text wrapping.

The Android layout had a nowrap approval badge in the same flex row as its
description, reducing the paragraph to one-word lines. These checks guard the
responsive source contract; real device screenshots remain a manual QA gate.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / 'business_frontend' / 'src'


def test_header_is_concise_and_uncluttered():
    source = (UI / 'PromotionConsole.jsx').read_text(encoding='utf-8')
    assert "<h3>{t('Create a campaign')}</h3>" in source
    assert 'Use your photo, refine the message and preview the offer before publishing.' in source
    assert 'Approval required before publishing' in source
    assert 'CREATIVE WORKSPACE · PRUVS BUSINESS' not in source
    assert 'Build from your real photograph, direct the creative' not in source
    assert 'Publishing remains a separate action.</p>' not in source
    assert 'pruvs-studio-2027-heading-copy' in source


def test_heading_is_grid_and_status_moves_below_at_tablet_sizes():
    styles = (UI / 'studio-2027.css').read_text(encoding='utf-8')
    assert 'display:grid;grid-template-columns:49px minmax(0,1fr) auto;' in styles
    assert '@media(max-width:1100px)' in styles
    assert 'grid-column:2;grid-row:2;justify-self:start;margin:0;' in styles
    assert 'max-width:100%;white-space:normal' in styles
    assert '.pruvs-ai-studio-heading{flex-wrap:wrap}' not in styles


def test_mobile_description_uses_entire_available_width():
    styles = (UI / 'studio-2027.css').read_text(encoding='utf-8')
    assert '@media(max-width:540px)' in styles
    assert 'grid-template-columns:minmax(0,1fr);gap:10px;' in styles
    assert 'grid-column:1;grid-row:1;min-width:0;' in styles
    assert 'grid-column:1;grid-row:2;' in styles
    assert 'word-break:normal;' in styles


def test_business_release_is_independent_of_core():
    api = (ROOT / 'business/main.py').read_text(encoding='utf-8')
    ui = (UI / 'main.jsx').read_text(encoding='utf-8')
    core = (ROOT / 'app/reliability.py').read_text(encoding='utf-8')
    assert "version='0.6.22'" in api
    assert 'Pruvs Business · v0.6.22' in ui
    assert 'RELEASE = "7.1.66"' in core


def test_campaign_library_is_contained_on_phone_widths():
    responsive = (UI / 'business-v0616-responsive.css').read_text(encoding='utf-8')
    library = (UI / 'campaign-library-v0615.css').read_text(encoding='utf-8')
    assert '.pruvs-business-2027{width:100%;overflow-x:clip}' in responsive
    assert 'display:grid;grid-template-columns:minmax(0,1fr);align-items:stretch' in responsive
    assert 'position:static;width:100%;justify-content:center' in responsive
    assert 'display:flex;flex-wrap:nowrap;width:100%;min-width:0;max-width:100%' in responsive
    assert 'width:100%;min-width:0;max-width:100%' in library


def test_romanian_campaign_and_overview_copy_is_complete():
    translations = (UI / 'i18n.jsx').read_text(encoding='utf-8')
    overview = (UI / 'MerchantOverview.jsx').read_text(encoding='utf-8')
    for key in ('Short video', 'Animated GIF', 'Registered merchant locations',
                'Open Campaign Studio', 'Your workspace at a glance',
                'AI generation may incur provider charges. The merchant reviews every promotion.'):
        assert key in translations
        assert f"t('{key}')" in overview or key in ('Short video', 'Animated GIF')
    assert 'const {t}=useBusinessLanguage();' in overview


def test_expired_merchant_session_is_not_reported_as_google_maps_failure():
    places = (UI / 'merchantPlaces.js').read_text(encoding='utf-8')
    shell = (UI / 'main.jsx').read_text(encoding='utf-8')
    assert "response.status===401" in places
    assert "pruvs-business-auth-expired" in places
    assert "res.status===401" in shell
    assert "window.addEventListener('pruvs-business-auth-expired',expire)" in shell
    assert "setToken('');setMe(null);setModal('')" in shell


def test_transient_readiness_failure_does_not_hide_google_search():
    places = (UI / 'merchantPlaces.js').read_text(encoding='utf-8')
    assert "const canLink=readiness?.unreachable===true||" in places
    assert "readiness?.places_search_enabled===true&&readiness?.place_links_migrated===true" in places
