"""Regression tests: AI campaign format, published-program invariants, still images."""
import json
import pytest
from fastapi import HTTPException
from business.ai_campaign_v067 import parse_generated_draft


def provider_response(fields):
    return {'status':'completed','output':[{'type':'message','content':[
        {'type':'output_text','text':json.dumps(fields)}]}]}


def valid_fields():
    return {
      'headline':'Your breakfast reward awaits',
      'message':'Eligible purchases count only after merchant verification.',
      'cta':'Explore the program',
      'alt_text':'A breakfast loyalty promotion card',
      'visual_brief':'A clean 4:5 card for a cafe loyalty campaign.',
      'motion_storyboard':'Animated text fades in over three seconds.',
      'watermark_text':'Provider-changed watermark',
    }


def test_still_image_accepts_empty_storyboard_and_overrides_watermark():
    data=valid_fields()
    data['motion_storyboard']=''
    result=parse_generated_draft(provider_response(data),'image','Pruvs Business')
    assert result.motion_storyboard=='Static image; no animation.'
    assert result.watermark_text=='Pruvs Business'
    assert result.message==data['message']


def test_motion_media_still_requires_real_storyboard():
    data=valid_fields()
    data['motion_storyboard']=''
    with pytest.raises(ValueError,match='format mismatch'):
        parse_generated_draft(provider_response(data),'video','Pruvs Business')


def test_field_bounds_are_not_silently_ignored():
    data=valid_fields()
    data['cta']='X'
    with pytest.raises(ValueError,match='format mismatch'):
        parse_generated_draft(provider_response(data),'image','Pruvs Business')


def test_malformed_response_is_rejected():
    invalid={'output':[{'content':[{'type':'output_text','text':'not-json'}]}]}
    with pytest.raises(ValueError,match='format mismatch'):
        parse_generated_draft(invalid,'image','Pruvs Business')


def test_incomplete_response_reports_specific_failure():
    with pytest.raises(HTTPException) as failure:
        parse_generated_draft({'status':'incomplete','output':[]},'image','Pruvs Business')
    assert failure.value.status_code==502
    assert 'interrupted' in failure.value.detail


def test_valid_draft_is_preserved():
    data=valid_fields()
    result=parse_generated_draft(provider_response(data),'gif','Merchant Brand')
    assert result.headline==data['headline']
    assert result.motion_storyboard==data['motion_storyboard']
    assert result.watermark_text=='Merchant Brand'
