"""Standalone release verification for reconciliation, identity and schema.
Run from installed backend: python .../tests/test_v7_1_14.py
"""
import importlib,pkgutil,sys,types,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Mock only external network SDK wrappers, not OCR normalization logic.
if 'app.services.ocr_providers.azure_receipt_provider' not in sys.modules:
    m=types.ModuleType('app.services.ocr_providers.azure_receipt_provider')
    m.AzureReceiptOCRProvider=type('AzureReceiptOCRProvider',(),{})
    sys.modules[m.__name__]=m
m=types.ModuleType('app.services.receipt_translation_service')
m.translate_receipt_item_names=lambda names:SimpleNamespace(error=None,translated_names={},source_language='en')
sys.modules[m.__name__]=m
from app.services.azure_receipt_direct_service import (build_receipt_structure,apply_basket_adjustments_proportionally,
                                                       classify_receipt_line,finalize_receipt_items,MONEY_TOLERANCE)
from app.services.receipt_identity import identity_hash,extract_from_text
from app.db.database import Base
import app.models
for module in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module('app.models.'+module.name)

def line(name,price):
    return SimpleNamespace(name=name,total_price=price,unit_price=price,quantity=1,currency='RON')
def normalized(lines,receipt_total):
    s=build_receipt_structure([line(n,p) for n,p in lines]);
    apply_basket_adjustments_proportionally(s,receipt_total=receipt_total)
    return finalize_receipt_items(s),s

class ReceiptReconciliationTests(unittest.TestCase):
    def test_do_not_invent_tax(self):
        items,s=normalized([('Fish and Chips',60),('Fries',40)],100)
        self.assertEqual([i['name'] for i in items],['Fish and Chips','Fries'])
        self.assertAlmostEqual(sum(i['total_price'] for i in items),100)
    def test_explicit_charge_keeps_names_clean(self):
        items,s=normalized([('Fish and Chips',60),('Fries',40),('Taxa serviciu',10)],110)
        self.assertEqual([i['name'] for i in items],['Fish and Chips','Fries','Taxa serviciu'])
        self.assertEqual([i['total_price'] for i in items],[60,40,10])
        self.assertEqual(round(sum(i['total_price'] for i in items),2),110)
        self.assertEqual(len(s['applied_basket_adjustments']),1)
    def test_vat_already_included_not_double_counted(self):
        items,s=normalized([('Fish and Chips',60),('Fries',40),('TVA 9%',8.26)],100)
        self.assertEqual(round(sum(i['total_price'] for i in items),2),100)
        self.assertEqual(len(items),2)
    def test_adjustment_not_applied_if_receipt_already_balances(self):
        items,s=normalized([('Fish and Chips',60),('Fries',40),('Taxa serviciu',10)],100)
        self.assertEqual(round(sum(i['total_price'] for i in items),2),100)
        self.assertEqual(len(s['ignored_basket_adjustments']),1)
    def test_mismatch_remains_mismatch(self):
        items,s=normalized([('Fish and Chips',60),('Fries',40)],90)
        self.assertGreater(abs(sum(i['total_price'] for i in items)-90),MONEY_TOLERANCE)
    def test_product_contains_word_serviciu_not_a_tax(self):
        self.assertEqual(classify_receipt_line('Serviciu catering',40),'product')
        self.assertEqual(classify_receipt_line('Tipar color',10),'product')
        self.assertEqual(classify_receipt_line('Ambalaj pizza',3),'product')
    def test_carrefour_pet_deposit_keeps_original_product_prices(self):
        lines=[('GARANTIE PET',1.00),('VITAMIN AQUA CA 0.6',6.79),
               ('AQUA CARPATICA APA M',3.79),('OREZ LAPTE 200G FRU',6.89),
               ('SALATA DE PASTE CU',9.03),('CHIFTELE DE PORC 220',10.37),
               ('HUMUS CU PESTO 200G',8.69),('SACOSA MAIEU MICA',1.15)]
        items,structure=normalized(lines,47.71)
        self.assertEqual(len(items),8)
        self.assertEqual([round(i['total_price'],2) for i in items],[1,6.79,3.79,6.89,9.03,10.37,8.69,1.15])
        self.assertEqual(round(sum(i['total_price'] for i in items),2),47.71)
        self.assertFalse(any('Taxa/Ajustare bon' in i['name'] for i in items))
    def test_missing_pet_deposit_cannot_be_fabricated(self):
        items,structure=normalized([('VITAMIN AQUA CA 0.6',6.79),
            ('AQUA CARPATICA APA M',3.79),('OREZ LAPTE 200G FRU',6.89),
            ('SALATA DE PASTE CU',9.03),('CHIFTELE DE PORC 220',10.37),
            ('HUMUS CU PESTO 200G',8.69),('SACOSA MAIEU MICA',1.15)],47.71)
        self.assertEqual(round(sum(i['total_price'] for i in items),2),46.71)
        self.assertEqual(len(items),7)
    def test_fiscal_semantic_key(self):
        txt='BON FISCAL NR 002183\nDATA 19.10.2026\nTOTAL 190.00'
        i=extract_from_text(txt)
        self.assertEqual(i['number'],'002183')
        k=identity_hash('Zest Food',190,'RON',i['date'],i['number'])
        self.assertEqual(k,identity_hash('ZEST FOOD',190.00,'RON',i['date'],i['number']))
        self.assertNotEqual(k,identity_hash('ZEST FOOD',190.00,'RON',i['date'],'002184'))
        self.assertIsNone(identity_hash('ZEST FOOD',190,'RON',None,i['number']))
    def test_schema_models(self):
        e=create_engine('sqlite:///:memory:')
        Base.metadata.create_all(e)
        self.assertIn('pruvs_receipt_identities',Base.metadata.tables)
        self.assertIn('pruvs_referral_reward_policy',Base.metadata.tables)
        self.assertIn('pruvs_ocr_bonus_grants',Base.metadata.tables)
        e.dispose()

if __name__=='__main__':unittest.main(verbosity=2)
