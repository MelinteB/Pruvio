import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { BillFlowNav, itemAllocationState } from './professional/CorePages';

afterEach(() => cleanup());

describe('Pruvs v7.1.24 item completion and sticky overview', () => {
  it('marks the current participant selection green without requiring full allocation', () => {
    const state = itemAllocationState({quantity:2,remaining_quantity:1,assignments:[{participant_id:7,quantity:1}]},7);
    expect(state.selectedByMe).toBe(true);
    expect(state.fullyAllocated).toBe(false);
    expect(state.own).toBe(1);
    expect(state.max).toBe(2);
  });
  it('marks fully allocated items for any participant but never claims bank payment', () => {
    const state = itemAllocationState({quantity:2,remaining_quantity:0,assignments:[{participant_id:8,quantity:2}]},7);
    expect(state.fullyAllocated).toBe(true);
    expect(state.selectedByMe).toBe(false);
    expect(state.unavailable).toBe(true);
  });
  it('converts numeric string quantities before adding assigned plus remaining', () => {
    const state = itemAllocationState({quantity:'3',remaining_quantity:'2',assignments:[{participant_id:7,quantity:'1'}]},7);
    expect(state.max).toBe(3);
    expect(state.own).toBe(1);
  });
  it('does not mark zero-quantity items complete', () => {
    const state = itemAllocationState({quantity:0,remaining_quantity:0,assignments:[]},7);
    expect(state.fullyAllocated).toBe(false);
    expect(state.selectedByMe).toBe(false);
  });
  it('only shows Select items and People as primary views', () => {
    render(<BillFlowNav active="items" onChange={vi.fn()}/>);
    expect(screen.getAllByRole('tab')).toHaveLength(2);
    expect(screen.queryByRole('tab',{name:/summary/i})).toBeNull();
  });
});
