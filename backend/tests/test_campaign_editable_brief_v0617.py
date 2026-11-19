"""Editable campaign directions must precede AI generation and never replace rules."""
from pathlib import Path
import pytest
from pydantic import ValidationError
from business.ai_campaign_v067 import CampaignBrief

ROOT=Path(__file__).resolve().parents[1]


def brief(**changes):
    values=dict(program_id='12345678-1234-4234-9234-1234567890ab',
                goal='Encourage loyal customers to return',
                audience='Local regulars',tone='friendly',format='image',
                duration_days=14,watermark_text='Pruvs Business')
    values.update(changes)
    return CampaignBrief(**values)


def test_custom_campaign_instructions_are_accepted_and_bounded():
    text='A welcoming invitation for customers who enjoy morning coffee.'
    assert brief(creative_instructions=text).creative_instructions==text
    assert brief().creative_instructions==''
    with pytest.raises(ValidationError):
        brief(creative_instructions='x'*1201)


def test_locked_program_terms_are_still_server_authoritative():
    src=(ROOT/'business/ai_campaign_v067.py').read_text(encoding='utf-8')
    assert "'merchant_creative_brief':payload.creative_instructions.strip()" in src
    for key in ('minimum_purchase_minor','qualifying_purchases_required','reward_minor'):
        assert "'"+key+"':" in src
    assert 'locked program' in src
    assert 'always take precedence' in src


def test_studio_exposes_editable_predefined_text_before_generation():
    src=(ROOT/'business_frontend/src/PromotionConsole.jsx').read_text(encoding='utf-8')
    assert 'predefinedCampaignBrief' in src
    assert 'creative_instructions:creativeInstructions.trim()' in src
    assert 'Predefined campaign text · edit before generating' in src
    assert 'Restore predefined text' in src
    assert 'Campaign copy · review and edit before generating artwork' in src
    assert src.index('id="pruvs-campaign-brief"')<src.index('onClick={generateDraft}')
    assert src.index('Campaign copy · review')<src.index('onClick={generateAIArtwork}')
    assert 'Program conditions (locked)' in src
    assert '/v1/merchant/promotions/media/upload' in src
    assert 'setMediaUrl(data.media_url)' in src


def test_merchant_copy_validation_without_publishing_automatically():
    src=(ROOT/'business_frontend/src/PromotionConsole.jsx').read_text(encoding='utf-8')
    assert 'headline.trim().length<5' in src
    assert 'message.trim().length<10' in src
    assert 'Publishing remains a separate merchant approval action' in src
    assert 'await call(\'/v1/merchant/promotions\',token,payload)' in src
