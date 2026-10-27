import React from 'react';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { groupMerchants } from './Receipts';
import { BillFlowNav } from './professional/CorePages';

// Vitest is not configured with global afterEach; explicitly unmount every render.
afterEach(() => cleanup());

describe('organized merchant receipt tree', () => {
  it('groups matching merchant names and orders newest scans first', () => {
    const history={group_order:[1,2,3],receipts:[
      {case_id:1,merchant_name:' Carrefour ',scan_date:'2026-10-21T12:00:00',original_filename:'a.jpg'},
      {case_id:2,merchant_name:'CARREFOUR',scan_date:'2026-10-26T11:00:00',original_filename:'b.jpg'},
      {case_id:3,merchant_name:'Coffee',scan_date:'2026-10-25T11:00:00',original_filename:'c.jpg'},
    ],bills:[{case_id:1,session_id:41,status:'settled'},{case_id:2,session_id:42,status:'open'}]};
    const result=groupMerchants(history);
    expect(result).toHaveLength(2);
    expect(result[0].key).toBe('carrefour');
    expect(result[0].receipts.map(r=>r.id)).toEqual([2,1]);
    expect(result[0].receipts[0].bills[0].session_id).toBe(42);
  });
  it('supports receipts shared without an owned receipt object',()=>{
    const result=groupMerchants({group_order:[19],receipts:[],bills:[{case_id:19,session_id:9,source_name:'Cafe',scan_date:'2026-10-27T09:00:00'}]});
    expect(result[0].receipts[0].receipt).toBe(null);
    expect(result[0].name).toBe('Cafe');
  });
});

describe('separate shared bill views',()=>{
  it('selects People without changing bill data',()=>{
    const onChange=vi.fn();
    render(<BillFlowNav active="items" onChange={onChange}/>);
    fireEvent.click(screen.getByRole('tab',{name:/people/i}));
    expect(onChange).toHaveBeenCalledWith('people');
  });
  it('allows Summary to be selected independently',()=>{
    const onChange=vi.fn();
    render(<BillFlowNav active="summary" onChange={onChange}/>);
    expect(screen.getByRole('tab',{name:/summary/i}).getAttribute('aria-selected')).toBe('true');
  });
});
