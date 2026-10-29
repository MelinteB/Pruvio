import React from 'react';
import { describe, it, expect, afterEach, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { ReceiptPaper } from './ReceiptPaper';

vi.mock('./i18n', () => ({ t: value => value }));

afterEach(() => cleanup());

const receipt = {
  merchant_name: 'Cafe Test', original_filename: 'scan-01.jpg', currency: 'RON',
  receipt_total: 45, calculated_total: 45,
  items: [
    { id: 1, name: 'Espresso', translated_name: '', quantity: 2, unit_price: 10, total_price: 20 },
    { id: 2, name: 'Croissant', translated_name: 'Corn', quantity: 1, unit_price: 25, total_price: 25 }
  ]
};

describe('v7.1.31 compact receipt presentation', () => {
  it('renders a paper-style receipt with compact semantic item rows', () => {
    const { container } = render(<ReceiptPaper receipt={receipt}/>);
    const paper = container.querySelector('.pruvs-thermal-receipt');
    expect(paper).not.toBeNull();
    expect(screen.getByRole('heading', {name: 'Cafe Test'})).not.toBeNull();
    const table = screen.getByRole('table');
    expect(within(table).getAllByRole('row')).toHaveLength(3);
    expect(within(table).getByText('Espresso')).not.toBeNull();
    expect(within(table).getByText('Croissant')).not.toBeNull();
    expect(within(table).getByText('Corn')).not.toBeNull();
    expect(within(table).getByText('2 × 10.00 RON')).not.toBeNull();
    expect(within(table).getByText('20.00 RON')).not.toBeNull();
    expect(within(table).getByText('25.00 RON')).not.toBeNull();
    expect(screen.getAllByText('45.00 RON')).toHaveLength(2);
  });
  it('does not mutate OCR values or silently assume the extracted total is correct', () => {
    const r = {...receipt, receipt_total: 50};
    render(<ReceiptPaper receipt={r}/>);
    expect(screen.getByRole('note').textContent).toMatch(/do not match/i);
    expect(screen.getByText('50.00 RON')).not.toBeNull();
    expect(r.calculated_total).toBe(45);
  });
  it('gracefully renders an empty receipt without adding fake products', () => {
    const {container} = render(<ReceiptPaper receipt={{...receipt,items:[]}}/>);
    expect(container.querySelectorAll('.pruvs-thermal-items tbody tr')).toHaveLength(0);
    expect(screen.getByText(/No items were extracted/)).not.toBeNull();
  });
});
