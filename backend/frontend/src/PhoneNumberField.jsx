import React, { useEffect, useMemo, useState } from 'react';
import './phone-number-field.css';

// Minimal offline fallback for first paint. The authoritative list and
// country-specific lengths come from /api/v1/phone/countries (python-phonenumbers).
const FALLBACK = [
  {country:'RO',calling_code:'+40',national_prefix:'0',possible_lengths:[9]},
  {country:'US',calling_code:'+1',national_prefix:'1',possible_lengths:[10]},
  {country:'GB',calling_code:'+44',national_prefix:'0',possible_lengths:[10]},
  {country:'FR',calling_code:'+33',national_prefix:'0',possible_lengths:[9]},
  {country:'DE',calling_code:'+49',national_prefix:'0',possible_lengths:[6,7,8,9,10,11,12,13]},
  {country:'IT',calling_code:'+39',national_prefix:'',possible_lengths:[6,7,8,9,10,11,12]},
];

function digits(value) { return String(value || '').replace(/\D/g,''); }

// A metadata-driven *length* preview, not identity or number ownership proof.
// The backend independently validates and converts to E.164 on submission.
export function phoneLengthError(phone, region, countries = FALLBACK) {
  const raw = String(phone || '').trim();
  if (!raw) return 'Phone number is required for sharing.';
  const entry = countries.find(x => x.country === region);
  if (!entry) return 'Choose a supported country code.';
  if (!/^(?:\+|00)?[\d\s().-]+$/.test(raw)) return 'Use numbers and standard separators only.';
  const calling = digits(entry.calling_code);
  let national = digits(raw);
  if (raw.startsWith('+') || raw.startsWith('00')) {
    const entered = raw.startsWith('00') ? national.slice(2) : national;
    if (!entered.startsWith(calling)) return 'Phone prefix does not match the selected country.';
    national = entered.slice(calling.length);
  } else if (entry.national_prefix && national.startsWith(entry.national_prefix)) {
    // Domestic trunk prefixes (e.g. RO 0, UK 0, US 1) aren't part of E.164.
    national = national.slice(entry.national_prefix.length);
  }
  const lengths = entry.possible_lengths || [];
  if (lengths.length && !lengths.includes(national.length)) {
    const expected = lengths.length <= 4 ? lengths.join(', ') : `${Math.min(...lengths)}–${Math.max(...lengths)}`;
    return `For ${region} (${entry.calling_code}), use ${expected} digits after the country prefix.`;
  }
  if (national.length < 3 || national.length + calling.length > 15) {
    return 'Phone number length is invalid for the selected country.';
  }
  return '';
}

function flag(region) {
  return region?.length === 2 ? String.fromCodePoint(...region.split('').map(char=>127397 + char.charCodeAt(0))) : '';
}

export default function PhoneNumberField({ phone = '', country = 'RO', onPhoneChange, onCountryChange, required = true }) {
  const [countries, setCountries] = useState(FALLBACK);
  const [touched, setTouched] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    fetch('/api/v1/phone/countries', {credentials:'same-origin', cache:'no-store'})
      .then(response => { if (!response.ok) throw Error('country-codes'); return response.json(); })
      .then(data => {
        if (active && Array.isArray(data.countries) && data.countries.length > 100) {
          setCountries(data.countries);
          setFailed(false);
        }
      })
      .catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  },[]);
  const displayNames = useMemo(() => {
    try { return new Intl.DisplayNames([navigator.language || 'en'], {type:'region'}); }
    catch { return new Intl.DisplayNames(['en'], {type:'region'}); }
  }, []);
  const sorted = useMemo(() => [...countries].sort((a,b) => (
    (displayNames.of(a.country) || a.country).localeCompare(displayNames.of(b.country) || b.country)
  )), [countries,displayNames]);
  const selected = countries.find(entry => entry.country === country);
  const error = touched ? phoneLengthError(phone,country,countries) : '';
  return <div className="phone-enrollment-field">
    <label className="phone-enrollment-label" htmlFor="pruvs-phone-national">Phone number</label>
    <small className="phone-enrollment-reason">Required for sharing receipts and bills</small>
    <div className="phone-enrollment-controls">
      <select
        aria-label="Phone country and dialing prefix"
        value={country}
        onChange={e => { onCountryChange(e.target.value); setTouched(true); }}
      >
        {sorted.map(entry => <option key={entry.country} value={entry.country}>
          {`${flag(entry.country)} ${displayNames.of(entry.country) || entry.country} (${entry.calling_code})`}
        </option>)}
      </select>
      <div className="phone-enrollment-national">
        <span className="phone-enrollment-prefix" aria-hidden="true">{selected?.calling_code || ''}</span>
        <input
          id="pruvs-phone-national"
          type="tel"
          name="phone_number"
          inputMode="tel"
          autoComplete="tel-national"
          placeholder={country === 'RO' ? '722 123 456' : 'National number'}
          value={phone}
          required={required}
          maxLength={34}
          aria-invalid={Boolean(error)}
          aria-describedby="pruvs-phone-hint"
          onChange={e => {onPhoneChange(e.target.value); setTouched(true);}}
          onBlur={() => setTouched(true)}
        />
      </div>
    </div>
    <small className={'phone-enrollment-hint' + (error ? ' phone-enrollment-error' : '')} id="pruvs-phone-hint" role={error ? 'alert' : undefined}>
      {error || (selected ? `Country prefix ${selected.calling_code} · number checked for ${country}` : 'Choose your country')}
    </small>
    {failed && <small className="phone-enrollment-hint">Full country list is unavailable; showing common countries.</small>}
  </div>;
}
