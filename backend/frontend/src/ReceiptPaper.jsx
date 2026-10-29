import React from 'react';
import { money } from './api';
import { t } from './i18n';

/** Presentation only: show the values saved from OCR without recalculating or editing them. */
export function ReceiptPaper({ receipt }) {
  const items = Array.isArray(receipt?.items) ? receipt.items : [];
  const merchant = receipt?.merchant_name || t('Receipt');
  const currency = receipt?.currency;
  const amount = value => money(value, currency);
  const validTotal = Number.isFinite(Number(receipt?.receipt_total));
  const validExtracted = Number.isFinite(Number(receipt?.calculated_total));
  const mismatch = validTotal && validExtracted && Math.abs(Number(receipt.receipt_total) - Number(receipt.calculated_total)) > .02;
  return (
    <section className="pruvs-thermal-wrap" aria-label={t('Receipt items')}>
      <div className="pruvs-thermal-receipt">
        <header className="pruvs-thermal-header">
          <div className="pruvs-thermal-eyebrow">{t('Receipt')}</div>
          <h2>{merchant}</h2>
          {receipt?.original_filename && <p className="pruvs-thermal-reference">{receipt.original_filename}</p>}
        </header>
        <div className="pruvs-thermal-rule" aria-hidden="true" />
        <table className="pruvs-thermal-items">
          <thead>
            <tr>
              <th scope="col">{t('Item')}</th>
              <th scope="col">{t('Amount')}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, index) => (
              <tr key={item.id ?? `${index}-${item.name}`}>
                <td className="pruvs-thermal-item-detail">
                  <span className="pruvs-thermal-item-name">{item.name}</span>
                  {item.translated_name && item.translated_name !== item.name &&
                    <span className="pruvs-thermal-translation">{item.translated_name}</span>}
                  <span className="pruvs-thermal-unit">{item.quantity} × {amount(item.unit_price)}</span>
                </td>
                <td className="pruvs-thermal-item-total">{amount(item.total_price)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!items.length && <p className="pruvs-thermal-empty">{t('No items were extracted. Try uploading a clearer image.')}</p>}
        <div className="pruvs-thermal-rule" aria-hidden="true" />
        <div className="pruvs-thermal-summary">
          <span>{t('Items')} <span className="pruvs-thermal-count">{items.length}</span></span>
          <span>{t('Extracted items total')} <strong>{amount(receipt?.calculated_total)}</strong></span>
          <div className="pruvs-thermal-grand-total"><strong>{t('Receipt total')}</strong><strong>{amount(receipt?.receipt_total)}</strong></div>
        </div>
        {mismatch && <p className="pruvs-thermal-review" role="note">{t('The extracted items do not match the receipt total. Review the original receipt before splitting.')}</p>}
        <footer className="pruvs-thermal-footer">{t('Extracted from receipt · check against the original')}</footer>
      </div>
    </section>
  );
}
