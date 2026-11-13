"""Database-isolated regression tests: Wallet works on pre-b10 schema."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from business.wallet_reads_v068 import membership_rows, reward_rows

def legacy_schema():
    engine=create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text(
          "CREATE TABLE loyalty_programs (id TEXT PRIMARY KEY,title TEXT,"
          "stamps_required INTEGER,status TEXT)"))
        connection.execute(text(
          "CREATE TABLE loyalty_memberships (id TEXT PRIMARY KEY,"
          "consumer_id TEXT,program_id TEXT,stamps INTEGER)"))
        # Deliberately excludes b10's source_claim_id column.
        connection.execute(text(
          "CREATE TABLE loyalty_rewards (id TEXT PRIMARY KEY,consumer_id TEXT,"
          "program_id TEXT,status TEXT,redemption_code TEXT,reserved_until DATETIME)"))
        connection.execute(text(
          "INSERT INTO loyalty_programs VALUES ('p1','Two coffees',2,'published')"))
        connection.execute(text(
          "INSERT INTO loyalty_memberships VALUES ('m1','customer1','p1',1)"))
        connection.execute(text(
          "INSERT INTO loyalty_rewards VALUES ('r1','customer1','p1','available',NULL,NULL)"))
    return engine

def test_wallet_reads_legacy_schema_without_source_claim_id():
    engine=legacy_schema()
    with Session(engine) as db:
        memberships=membership_rows(db,'customer1')
        rewards=reward_rows(db,'customer1')
    assert memberships==[{'program_id':'p1','stamps':1,'title':'Two coffees',
                          'stamps_required':2,'status':'published'}]
    assert rewards==[{'id':'r1','program_id':'p1','status':'available',
                      'code':None,'reserved_until':None}]

def test_memberships_and_rewards_remain_scoped_to_customer():
    engine=legacy_schema()
    with Session(engine) as db:
        assert membership_rows(db,'another_user')==[]
        assert reward_rows(db,'another_user')==[]
