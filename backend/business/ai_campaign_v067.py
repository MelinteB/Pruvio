"""Merchant-controlled AI campaign draft assistant, no automatic publication or discounts."""
from __future__ import annotations
import json, os
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from .db import get_db
from .models import Program,Store,Merchant,Staff
from .security import merchant_actor

router=APIRouter(tags=['Campaign Studio AI'])

class CampaignBrief(BaseModel):
    program_id:str=Field(min_length=36,max_length=36)
    goal:str=Field(min_length=8,max_length=300)
    audience:str=Field(default='Local regular customers',min_length=3,max_length=140)
    tone:str=Field(default='friendly',pattern='^(friendly|premium|playful|professional)$')
    format:str=Field(default='image',pattern='^(image|gif|video)$')
    duration_days:int=Field(default=14,ge=1,le=90)
    watermark_text:str=Field(default='Pruvs Business',max_length=70)

SCHEMA={'type':'object','additionalProperties':False,'properties':{
    'headline':{'type':'string'},'message':{'type':'string'},
    'cta':{'type':'string'},'alt_text':{'type':'string'},
    'visual_brief':{'type':'string'},'motion_storyboard':{'type':'string'},
    'watermark_text':{'type':'string'}},
    'required':['headline','message','cta','alt_text','visual_brief','motion_storyboard','watermark_text']}

class GeneratedDraft(BaseModel):
    headline:str=Field(min_length=5,max_length=100)
    message:str=Field(min_length=10,max_length=500)
    cta:str=Field(min_length=3,max_length=42)
    alt_text:str=Field(min_length=5,max_length=160)
    visual_brief:str=Field(min_length=12,max_length=300)
    motion_storyboard:str=Field(min_length=5,max_length=400)
    watermark_text:str=Field(max_length=70)

@router.post('/v1/merchant/promotions/ai-draft')
def ai_draft(payload:CampaignBrief,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    if staff.role not in ('owner','manager'):raise HTTPException(403,'Merchant manager role required')
    if os.getenv('PRUVS_BUSINESS_AI_CAMPAIGNS_ENABLED','false').lower()!='true':
        raise HTTPException(503,'AI Campaign Studio has not been enabled on this staging service')
    secret=os.getenv('OPENAI_API_KEY','').strip()
    if not secret:raise HTTPException(503,'OpenAI API key is not configured on the backend')
    program=db.get(Program,payload.program_id)
    if not program or program.merchant_id!=staff.merchant_id or program.status!='published':
        raise HTTPException(404,'Choose an existing published merchant loyalty program')
    merchant=db.get(Merchant,staff.merchant_id)
    store=db.get(Store,program.store_id)
    if not merchant or not store or not store.active:
        raise HTTPException(409,'Merchant store is unavailable')
    from .pilot_v05 import campaign_schema_ready
    campaign_schema_ready(db)  # Do not bill AI if the campaign cannot be saved.
    facts={
      'merchant':merchant.name,'location':store.name,
      'program_title':program.title,'program_description':program.description,
      'currency':program.currency,'minimum_purchase_minor':program.min_purchase_minor,
      'qualifying_purchases_required':program.stamps_required,
      'reward_minor':program.reward_minor,
      'goal':payload.goal,'audience':payload.audience,'tone':payload.tone,
      'format':payload.format,'duration_days':payload.duration_days,
      'requested_watermark':payload.watermark_text.strip() or 'Pruvs Business'
    }
    instructions=('You write merchant-reviewed advertising copy for the Pruvs loyalty app. '
      'Return only JSON with the specified keys. Use only the provided merchant facts. '
      'Do not invent prices, discounts, eligibility, dates, payment integration, '
      'limited stock, independent verification or guaranteed rewards. '
      'Clearly explain that only merchant-verified purchases count toward the reward. '
      'Avoid financial promises. Headlines are short. Image brief describes a 4:5 vertical '
      'mobile display with text-safe margins. Motion storyboard is a simple 3-second '
      'animated card with no copyrighted imagery. Watermark must be the requested watermark.')
    body={
       'model':os.getenv('PRUVS_CAMPAIGN_AI_MODEL','gpt-6-luna'),
       'instructions':instructions,
       'input':json.dumps(facts,ensure_ascii=False),
       'max_output_tokens':1600,
       'text':{'format':{'type':'json_schema','name':'pruvs_campaign_draft',
                         'strict':True,'schema':SCHEMA}}
    }
    req=Request('https://api.openai.com/v1/responses',
        data=json.dumps(body).encode('utf-8'),method='POST',
        headers={'Authorization':'Bearer '+secret,'Content-Type':'application/json'})
    try:
        with urlopen(req,timeout=18) as response:
            payload_json=json.loads(response.read(100_000))
    except (HTTPError,URLError,TimeoutError,ValueError):
        raise HTTPException(502,'AI campaign draft could not be generated; check API configuration.') from None
    if payload_json.get('status')=='incomplete':
        raise HTTPException(502,'AI campaign draft was interrupted. Please retry or shorten the goal.')
    segments=[c.get('text','') for item in payload_json.get('output',[])
                for c in item.get('content',[]) if c.get('type')=='output_text']
    if not segments:raise HTTPException(502,'AI provider did not return a campaign draft')
    try:result=GeneratedDraft.model_validate_json(''.join(segments))
    except (ValueError,TypeError):
        raise HTTPException(502,'AI draft did not match the Pruvs campaign format') from None
    result.watermark_text=payload.watermark_text.strip() or 'Pruvs Business'
    return {'draft':result.model_dump(),'criteria':facts,
            'review_required':True,'published':False,
            'note':'Merchant must review the draft. No reward or campaign is published automatically.'}
