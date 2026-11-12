"""Isolated schema readiness tests with in-memory SQLite; never touch staging or production."""
from sqlalchemy import create_engine,text
from business.schema_readiness import check_schema

def test_reports_unmigrated_schema():
    engine=create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE loyalty_promotions (id TEXT)'))
    assert check_schema(engine)=={'campaign_media':False,'customer_codes':False}

def test_detects_additive_campaign_media_without_claim_code_table():
    engine=create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE loyalty_promotions (id TEXT, media_url TEXT, media_type TEXT, media_alt TEXT)'))
    assert check_schema(engine)=={'campaign_media':True,'customer_codes':False}

def test_detects_complete_staging_schema():
    engine=create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE loyalty_promotions (id TEXT, media_url TEXT, media_type TEXT, media_alt TEXT)'))
        conn.execute(text('CREATE TABLE loyalty_customer_claim_codes_v12 (claim_id TEXT)'))
    assert all(check_schema(engine).values())
