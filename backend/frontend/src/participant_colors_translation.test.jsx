import { afterEach, describe, expect, it } from 'vitest';
import { PARTICIPANT_PALETTE, participantColors, participantStyle, itemShareGradient } from './participant-colors';
import { setLanguage, t } from './i18n';

afterEach(()=>setLanguage('en'));

describe('Pruvs 7.1.27 participant colors and Romanian language',()=>{
  const participants=[{participant_id:33},{participant_id:11},{participant_id:22}];
  it('uses soft colors consistently when participants reorder',()=>{
    const a=participantColors(participants);
    const b=participantColors([...participants].reverse());
    expect(a).toEqual(b);
    expect(a['11']).not.toEqual(a['22']);
    expect(PARTICIPANT_PALETTE.length).toBeGreaterThanOrEqual(8);
    expect(participantStyle(a,22)['--participant-soft']).toMatch(/^#/);
  });
  it('shows each person’s actual percentage in multi-share gradient',()=>{
    const colors=participantColors(participants);
    const gradient=itemShareGradient({quantity:4,assignments:[{participant_id:11,quantity:1},{participant_id:22,quantity:3}]},colors);
    expect(gradient).toContain('0.00% 25.00%');
    expect(gradient).toContain('25.00% 100.00%');
    expect(gradient).toContain(colors['11'].soft);
    expect(gradient).toContain(colors['22'].soft);
  });
  it('shows unallocated quantities neutrally and ignores invalid quantities',()=>{
    const colors=participantColors(participants);
    const g=itemShareGradient({quantity:4,assignments:[{participant_id:11,quantity:1}]},colors);
    expect(g).toContain('#f6f8fd 25.00% 100%');
    expect(itemShareGradient({quantity:0,assignments:[]},colors)).toBeNull();
  });
  it('translates new user-facing screens to Romanian',()=>{
    setLanguage('ro');
    expect(t('Payment history')).toBe('Istoricul plăților');
    expect(t('Invite more people')).toBe('Invită mai multe persoane');
    expect(t('Fully allocated')).toBe('Repartizat complet');
    expect(t('Confirm received')).toBe('Confirmă încasarea');
    expect(document.documentElement.lang).toBe('ro');
  });
  it('preserves English and does not translate user-provided receipt names',()=>{
    setLanguage('en');
    expect(t('Confirm received')).toBe('Confirm received');
    setLanguage('ro');
    expect(t('Cafe custom item 8912')).toBe('Cafe custom item 8912');
  });
});
