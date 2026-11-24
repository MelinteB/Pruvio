import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import PhoneNumberField, { phoneLengthError } from './PhoneNumberField';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('mandatory international phone enrollment', () => {
  it('checks national length based on the chosen country, not a global 10-digit rule', () => {
    expect(phoneLengthError('0722 123 456','RO')).toBe('');
    expect(phoneLengthError('722123456','RO')).toBe('');
    expect(phoneLengthError('+40 722123456','RO')).toBe('');
    expect(phoneLengthError('07911 123456','GB')).toBe('');
    expect(phoneLengthError('(415) 555-2671','US')).toBe('');
    expect(phoneLengthError('06 12 34 56 78','FR')).toBe('');
    expect(phoneLengthError('0722 123','RO')).toContain('digits');
    expect(phoneLengthError('415 555','US')).toContain('digits');
    expect(phoneLengthError('+44 7911 123456','RO')).toContain('does not match');
    expect(phoneLengthError('', 'RO')).toContain('required');
  });

  it('shows a country selector and a mandatory phone input without duplicated prefixes', () => {
    vi.stubGlobal('fetch',vi.fn().mockRejectedValue(Error('offline')));
    const onPhoneChange = vi.fn();
    const onCountryChange = vi.fn();
    render(<PhoneNumberField
      phone="0722 123 456" country="RO"
      onPhoneChange={onPhoneChange} onCountryChange={onCountryChange}
    />);
    const phone=screen.getByLabelText('Phone number');
    expect(phone.required).toBe(true);
    expect(phone.value).toBe('0722 123 456');
    expect(screen.getByLabelText('Phone country and dialing prefix').value).toBe('RO');
    expect(screen.getByText('+40')).toBeTruthy();
    fireEvent.change(phone,{target:{value:'0722 123 45'}});
    expect(onPhoneChange).toHaveBeenCalledWith('0722 123 45');
    fireEvent.change(screen.getByLabelText('Phone country and dialing prefix'),{target:{value:'GB'}});
    expect(onCountryChange).toHaveBeenCalledWith('GB');
  });

  it('loads the server country list without removing the Romanian default', async () => {
    const mockCountries = Array.from({length:101},(_,i)=>({
      country: 'X'+i, calling_code: '+999', possible_lengths:[9]
    }));
    mockCountries[0]={country:'RO',calling_code:'+40',national_prefix:'0',possible_lengths:[9]};
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue({
      ok:true, json:async()=>({countries:mockCountries})
    }));
    render(<PhoneNumberField phone="" country="RO" onPhoneChange={vi.fn()} onCountryChange={vi.fn()} />);
    expect(screen.getByLabelText('Phone number').required).toBe(true);
  });
});
