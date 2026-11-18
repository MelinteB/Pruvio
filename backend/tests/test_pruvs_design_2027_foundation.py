"""Cross-app 2027 design parity and safety contracts.

CSS and JSX source assertions cover shared design sources, WYSIWYG preview,
merchant approval wording, accessibility guardrails, and no payment behavior
changes. Browser/device checks remain a separate release gate.
"""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT/path).read_text(encoding='utf-8')


def test_shared_tokens_loaded_after_legacy_styles_by_both_applications():
    tokens=read('shared_ui/pruvs-2027-tokens.css')
    business=read('business_frontend/src/main.jsx')
    core=read('frontend/src/main.jsx')
    assert '--pruvs-accent:' in tokens
    assert '--pruvs-shadow:' in tokens
    assert 'prefers-reduced-motion:reduce' in tokens
    assert 'prefers-contrast:more' in tokens
    assert "import '../../shared_ui/pruvs-2027-tokens.css'" in business
    assert "import '../../shared_ui/pruvs-2027-tokens.css'" in core
    assert "import './business-2027.css'" in business
    assert "import './core-2027.css'" in core


def test_core_promotion_and_business_preview_share_the_same_card_styles():
    customer=read('frontend/src/PromotionsPreview.jsx')
    creative=read('frontend/src/CampaignCreative.jsx')
    merchant=read('business_frontend/src/CorePromotionPreview.jsx')
    shared=read('shared_ui/pruvs-campaign-card-2027.css')
    for name in ('pruvs-promo','pruvs-campaign-creative','pruvs-campaign-creative-overlay',
                 'pruvs-campaign-creative-kicker','pruvs-promo-meta'):
        assert name in creative+customer
        assert name in merchant
    assert "import '../../frontend/src/promotions-preview.css'" in merchant
    assert "import '../../frontend/src/campaign-creative.css'" in merchant
    assert "import '../../shared_ui/pruvs-campaign-card-2027.css'" in merchant
    assert "import '../../shared_ui/pruvs-campaign-card-2027.css'" in read('frontend/src/main.jsx')
    assert ":is(.core-experience,.pruvs-core-preview-stage) .pruvs-promo" in shared
    assert "Same card layout, copy overlay and reward details used in Core." in merchant
    assert 'aria-pressed={viewport' in merchant
    assert 'Preview only' in merchant
    assert "See loyalty program" in customer and "See loyalty program" in merchant


def test_studio_draft_is_not_approved_and_media_failure_remains_blocking():
    studio=read('business_frontend/src/PromotionConsole.jsx')
    assert "import CorePromotionPreview from './CorePromotionPreview.jsx'" in studio
    assert "import './studio-2027.css'" in studio
    assert "Approval required" in studio
    assert "Merchant approved</span>" not in studio
    assert "preview does not" not in studio or "Previewing does not publish" in studio
    assert 'if(mediaCannotSave)' in studio
    assert 'setMediaPreviewError(true)' in studio
    assert "displayedMediaUrl===mediaUrl" in studio
    assert 'source_image_used' in studio
    assert "media_key:imageOrigin==='upload'?artworkKey:null" in studio
    assert 'creative_instructions:creativeInstructions.trim()' in studio
    assert 'AI generation is billed' not in studio or 'may incur provider charges' in studio


def test_navigation_and_login_do_not_ship_a_dummy_merchant_identity():
    main=read('business_frontend/src/main.jsx')
    assert "useState('merchant@example.test')" not in main
    assert "Merchant platform concept v0.2" not in main
    assert 'aria-label="Merchant workspace navigation"' in main
    assert 'aria-current={page===id?' in main
    assert 'aria-expanded={menu}' in main
    assert 'pruvs-business-nav-scrim' in main
    assert "e.key==='Escape'" in main


def test_pruvs_video_responds_to_reduced_motion_preference():
    customer=read('frontend/src/CampaignCreative.jsx')
    merchant=read('business_frontend/src/CorePromotionPreview.jsx')
    for source in (customer,merchant):
        assert "prefers-reduced-motion: reduce" in source
        assert 'autoPlay={!reduceMotion}' in source
        assert 'controls={reduceMotion}' in source
        assert "addEventListener?.('change',update)" in source


def test_design_foundation_is_responsive_and_no_new_payment_side_effects():
    business=read('business_frontend/src/studio-2027.css')
    core=read('frontend/src/core-2027.css')
    assert 'grid-template-columns:minmax(0,1fr) minmax(320px,410px)' in business
    assert '@media(max-width:1180px)' in business
    assert '@media(max-width:700px)' in business
    assert '@media(max-width:750px)' in core
    # No changes to backend receipt, settlement or loyalty state machines are necessary.
    assert "autoPlay" not in read('frontend/src/Bill.jsx')
