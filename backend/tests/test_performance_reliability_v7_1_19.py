"""Offline regression tests for Pruvs v7.1.19; no live API or DB required."""
import ast
import os
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from app.reliability import OCRCapacity, OCRBusy, RELEASE, bounded_integer

BACKEND = Path(__file__).resolve().parents[1]


class PerformanceReliabilityTests(unittest.TestCase):
    def test_release_version(self):
        self.assertEqual(RELEASE, '7.1.20')
        api = (BACKEND/'app/react_app/api.py').read_text(encoding='utf8')
        self.assertIn("'version':RELEASE", api)
        self.assertIn("version:'7.1.20'", (BACKEND/'frontend/scripts/stamp-build.mjs').read_text(encoding='utf8'))

    def test_bounded_ocr_capacity(self):
        gate = OCRCapacity(1)
        with gate.admit():
            with self.assertRaises(OCRBusy):
                with gate.admit():
                    self.fail('Should not acquire busy OCR slot')
        with gate.admit():
            pass
        with self.assertRaisesRegex(ValueError, 'positive'):
            OCRCapacity(0)

    def test_ocr_gate_releases_when_processing_throws(self):
        gate = OCRCapacity(1)
        with self.assertRaisesRegex(RuntimeError, 'provider'):
            with gate.admit():
                raise RuntimeError('provider failed')
        with gate.admit():
            pass

    def test_ocr_capacity_bounds(self):
        with patch.dict(os.environ, {'PRUVS_OCR_MAX_INFLIGHT': '100'}):
            self.assertEqual(bounded_integer('PRUVS_OCR_MAX_INFLIGHT',2,1,8),2)
        with patch.dict(os.environ, {'PRUVS_OCR_MAX_INFLIGHT': '3'}):
            self.assertEqual(bounded_integer('PRUVS_OCR_MAX_INFLIGHT',2,1,8),3)
        with patch.dict(os.environ, {'PRUVS_OCR_MAX_INFLIGHT': 'invalid'}):
            self.assertEqual(bounded_integer('PRUVS_OCR_MAX_INFLIGHT',2,1,8),2)

    def test_receipt_label_bulk_query_latest_wins(self):
        # Isolate the pure query helper because importing OCR providers requires
        # optional Azure dependencies not necessary for these tests.
        source = (BACKEND/'app/react_app/receipt_labels.py').read_text(encoding='utf8')
        fn = next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='receipt_labels')
        class Col:
            def in_(self,ids):return ('ids',tuple(ids))
            def desc(self):return ('desc',)
        class Model:
            id=Col()
            case_id=Col()
        class Query:
            def __init__(self,records):self.records=records;self.filters=[];self.orders=[]
            def filter(self,x):self.filters.append(x);return self
            def order_by(self,x):self.orders.append(x);return self
            def all(self):return self.records
        class Db:
            def __init__(self,records):self.query_calls=0;self.records=records
            def query(self,model):
                self.query_calls+=1
                self.model=model
                return Query(self.records)
        obj = SimpleNamespace
        ns={'ExternalOCRRequest':Model,'_parse_ocr_metadata':lambda record: {'merchant_name':record.name}}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'receipt_labels','exec'),ns)
        db=Db([obj(case_id=7,name=' New merchant '),obj(case_id=7,name='old merchant'),obj(case_id=9,name=None)])
        labels=ns['receipt_labels'](db,[7,9,12,7])
        self.assertEqual(labels,{7:'New merchant',9:'Receipt #9',12:'Receipt #12'})
        self.assertEqual(db.query_calls,1)
        empty=Db([])
        self.assertEqual(ns['receipt_labels'](empty,[]),{})
        self.assertEqual(empty.query_calls,0)

    def test_ocr_admission_precedes_credit_reservation(self):
        source=(BACKEND/'app/react_app/api.py').read_text(encoding='utf8')
        upload=source.split("@router.post('/receipts/upload')",1)[1].split('def owned_case(',1)[0]
        self.assertLess(upload.index('with ocr_capacity.admit():'), upload.index('token=reserve('))
        self.assertLess(upload.index('with ocr_capacity.admit():'),upload.index('file.file.read('))
        self.assertIn('finish(token,False)', upload)
        self.assertIn("headers={'Retry-After':'10'}", upload)

    def test_live_bill_retry_backoff_is_bounded(self):
        source=(BACKEND/'frontend/src/Bill.jsx').read_text(encoding='utf8')
        self.assertIn('Math.min(30000',source)
        self.assertIn('retryCount = 0',source)
        self.assertIn('e.code !== 1008',source)

    def test_batch_queries_in_summary_and_history(self):
        summary=(BACKEND/'app/react_app/bill_service.py').read_text(encoding='utf8')
        self.assertIn('referenced_user_ids',summary)
        self.assertIn('User.id.in_(referenced_user_ids)',summary)
        self.assertIn('linked_user = linked_users.get(',summary)
        history=(BACKEND/'app/react_app/api.py').read_text(encoding='utf8').split("@router.get('/history')",1)[1].split("@router.post('/receipts/upload')",1)[0]
        self.assertIn('receipt_labels(db,',history)
        self.assertIn('case_by_id=',history)
        self.assertNotIn('db.get(Case,',history)

if __name__ == '__main__':
    unittest.main()
