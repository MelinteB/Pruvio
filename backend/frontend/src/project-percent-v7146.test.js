import {describe,it,expect} from 'vitest';
import {distributeRemainder, percentagesComplete} from './project-percent-v7146.mjs';

describe('automatic Project percentage allocation',()=>{
  it('balances two participants when one is edited',()=>{
    const p=distributeRemainder([1,2],1,'20');expect(p[1]).toBe('20');expect(p[2]).toBe('80.00');
    expect(percentagesComplete([1,2],id=>p[id])).toBe(true);
  });
  it('balances three participants',()=>{
    const p=distributeRemainder([1,2,3],1,'20');expect([p[2],p[3]]).toEqual(['40.00','40.00']);
  });
  it('distributes integer basis-point remainder exactly',()=>{
    const ids=[1,2,3,4],p=distributeRemainder(ids,2,'33.33');
    expect(percentagesComplete(ids,id=>p[id])).toBe(true);
  });
  it('supports 100 percent for one person and zero for others',()=>{
    const p=distributeRemainder([1,2],2,'100');expect(p[1]).toBe('0.00');
  });
  it('rejects out-of-range and incomplete values on save',()=>{
    expect(distributeRemainder([1,2],1,'105')).toBeNull();
    expect(percentagesComplete([1,2],id=>id===1?'':'50')).toBe(false);
  });
});
