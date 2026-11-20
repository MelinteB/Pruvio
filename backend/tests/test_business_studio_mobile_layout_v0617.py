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
    assert "version='0.6.21'" in api
    assert 'Pruvs Business · v0.6.21' in ui
    assert 'RELEASE = "7.1.65"' in core
