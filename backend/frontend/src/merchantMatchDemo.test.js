import {describe,it,expect} from 'vitest';
import {normalizeMerchant,suggestedDemoPrograms,isStagingLoyaltyDemo} from './merchantMatchDemo';
const bistro={merchant_name:'Bistro Central',receipt_pilot_allowed:true,
  store:{name:'Breakfast rew'}, program:{id:'p1',title:'Breakfast rew · Bistro Central Rewards'}};
const billa={merchant_name:'Other merchant',receipt_pilot_allowed:true,
  store:{name:'Test location'}, program:{id:'p2',title:'Billa Rewards'}};
describe('Staging demo merchant name suggestions',()=>{
  it('removes Romanian accents and punctuation',()=>{
    expect(normalizeMerchant(' S.C. Bíllă  România S.R.L. ')).toBe('S C BILLA ROMANIA S R L');
  });
  it('suggests an approved and joined program containing the receipt merchant',()=>{
    expect(suggestedDemoPrograms('Bistro Central S.R.L.',[bistro],new Set(['p1']))).toEqual([bistro]);
    expect(suggestedDemoPrograms('S.C. BILLA ROMANIA S.R.L.',[billa],new Set(['p2']))).toEqual([billa]);
  });
  it('cannot suggest unjoined, disapproved, unrelated or generic merchant',()=>{
    expect(suggestedDemoPrograms('Bistro Central',[bistro],new Set())).toEqual([]);
    expect(suggestedDemoPrograms('Bistro Central',[{...bistro,receipt_pilot_allowed:false}],new Set(['p1']))).toEqual([]);
    expect(suggestedDemoPrograms('Carrefour Romania',[bistro],new Set(['p1']))).toEqual([]);
    expect(suggestedDemoPrograms('S.C. ROMANIA S.R.L.',[bistro],new Set(['p1']))).toEqual([]);
  });
  it('allows name matching on staging, never on pruvs.io',()=>{
    expect(isStagingLoyaltyDemo('pruvs-core-staging.onrender.com')).toBe(true);
    expect(isStagingLoyaltyDemo('pruvs.io')).toBe(false);
    expect(isStagingLoyaltyDemo('www.pruvs.io')).toBe(false);
  });
});
