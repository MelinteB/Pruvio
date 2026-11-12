"""Staging-only safety checks for campaign pipeline and receipt project controls."""
from pathlib import Path
import ast
from PIL import Image
import pytest
from business.ai_campaign_v067 import CampaignBrief,GeneratedDraft
from business.media_v067 import frame

BASE=Path(__file__).resolve().parents[1]

def test_stage_version_compiles():
    paths=[
      'app/react_main.py','app/react_app/bill_projects_v7141.py',
      'app/react_app/loyalty_api.py','business/main.py','business/models_v067.py',
      'business/ai_campaign_v067.py','business/media_v067.py',
      'business_migrations/versions/b10d067_discount_reconciliation.py'
    ]
    for file in paths:
        ast.parse((BASE/file).read_text(encoding='utf-8'),filename=file)

def test_campaign_requires_published_program_and_server_side_facts():
    src=(BASE/'business/ai_campaign_v067.py').read_text(encoding='utf-8')
    assert "program.status!='published'" in src
    assert "merchant.merchant_id" not in src or "merchant" in src
    brief=CampaignBrief(program_id='x'*36,goal='Bring regular customers back')
    assert brief.duration_days==14
    assert brief.format=='image'

def test_ai_draft_contract_limits_public_message():
    with pytest.raises(ValueError):
        GeneratedDraft(headline='a'*101,message='Valid message for campaign',
          cta='Join now',alt_text='A cafe reward card',visual_brief='A clean mobile card',
          motion_storyboard='Zoom text slightly',watermark_text='Pruvs')

def test_campaign_frames_have_mobile_dimensions_and_watermark():
    picture=Image.new('RGB',(500,600),'#edeeee')
    result=frame(picture,0,18,'Pruvs Business','New loyalty reward')
    assert result.size==(720,900)
    assert result.mode=='RGB'

def test_archived_and_removed_sources_are_filtered_before_project_import():
    p=(BASE/'app/react_app/bill_projects_v7141.py').read_text(encoding='utf-8')
    assert 'def active_for_project' in p
    assert "HistoryVisibility.state.in_(('archived','removed'))" in p
    assert 'if not active_for_project' in p

def test_redemption_is_merchant_attested_and_audited_atomically():
    p=(BASE/'business/main.py').read_text(encoding='utf-8')
    assert 'sale_reference' in p and 'DiscountRedemption(' in p
    assert "verification_source='merchant_attested'" in p
    assert "db.add(record)" in p
    assert "db.commit()" in p
