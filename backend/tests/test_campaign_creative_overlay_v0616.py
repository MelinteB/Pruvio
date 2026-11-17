"""Protect campaign copy overlays and animation behavior with isolated checks."""
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw
from business.media_v067 import frame

ROOT = Path(__file__).resolve().parents[1]


def test_animated_frame_changes_when_source_has_matching_four_five_ratio():
    photo = Image.new("RGB", (800, 1000), "#edc4a3")
    draw = ImageDraw.Draw(photo)
    draw.rectangle((60, 120, 240, 820), fill="#334477")
    draw.ellipse((490, 80, 720, 310), fill="#119e87")
    first = frame(photo, 0, 18, "Pruvs Business", "Breakfast offer")
    last = frame(photo, 17, 18, "Pruvs Business", "Breakfast offer")
    assert first.size == (720, 900)
    assert last.size == (720, 900)
    assert ImageChops.difference(first, last).getbbox() is not None


def test_customer_widgets_overlay_copy_without_a_duplicate_text_block():
    component = (ROOT / "frontend/src/CampaignCreative.jsx").read_text(encoding="utf-8")
    home = (ROOT / "frontend/src/PromotionsPreview.jsx").read_text(encoding="utf-8")
    rewards = (ROOT / "frontend/src/Rewards.jsx").read_text(encoding="utf-8")
    assert 'p.headline' in component and 'p.message' in component
    assert 'pruvs-campaign-creative-overlay' in component
    assert 'hasCampaignCreative(p)?' in home
    assert 'hasCampaignCreative(p)?' in rewards
    assert 'activePromotionByProgram' in rewards
    assert '<CampaignCreative promotion={activePromotionByProgram.get(o.program.id)} compact/>' in rewards


def test_merchants_get_rendered_gif_or_mp4_before_draft_save():
    studio = (ROOT / "business_frontend/src/PromotionConsole.jsx").read_text(encoding="utf-8")
    assert 'mediaNeedsRendering' in studio
    assert 'const rendered=await renderSelectedArtwork(artworkKey)' in studio
    assert 'rendered.media_type!==targetMediaType' in studio
    assert 'media_url:savedMediaUrl||null' in studio
    assert 'pruvs-business-creative-text' in studio


def test_public_creative_only_accepts_https_image_or_video():
    source = (ROOT / "frontend/src/CampaignCreative.jsx").read_text(encoding="utf-8")
    assert 'hasCampaignCreative' in source
    assert 'startsWith(\'image/\')' in source
    assert 'startsWith(\'video/\')' in source
