import React from 'react';
import { Mail } from 'lucide-react';
import './login-method-grid.css';

// These are Core consumer login methods. Pruvs Business merchant authentication is separate.
// Social methods stay disabled until a verified backend OAuth flow reports them enabled.
export const LOGIN_METHODS = Object.freeze([
  { id: 'email', label: 'Email' },
  { id: 'google', label: 'Google' },
  { id: 'yahoo', label: 'Yahoo' },
  { id: 'facebook', label: 'Facebook' },
  { id: 'instagram', label: 'Instagram' },
  { id: 'tiktok', label: 'TikTok' },
]);

function BrandMark({ provider }) {
  if (provider === 'email') return <Mail size={27} strokeWidth={2} aria-hidden="true" />;
  if (provider === 'google') return <svg viewBox="0 0 48 48" aria-hidden="true" focusable="false">
    <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.39 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
    <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.29 5.48-4.85 7.18l7.73 6C44.32 38.03 46.98 31.89 46.98 24.55z"/>
    <path fill="#FBBC05" d="M10.53 28.59A14.46 14.46 0 0 1 9.75 24c0-1.59.27-3.13.76-4.59l-7.97-6.2A23.87 23.87 0 0 0 0 24c0 3.87.93 7.53 2.56 10.79z"/>
    <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.82-5.8l-7.73-6c-2.15 1.45-4.92 2.3-8.09 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.97 6.2C6.51 42.62 14.62 48 24 48z"/>
  </svg>;
  if (provider === 'yahoo') return <svg viewBox="0 0 48 48" aria-hidden="true" focusable="false"><text x="24" y="35" textAnchor="middle" fontFamily="Arial,Helvetica,sans-serif" fontWeight="900" fontSize="35" fill="#6001D2">Y!</text></svg>;
  if (provider === 'facebook') return <svg viewBox="0 0 48 48" aria-hidden="true" focusable="false"><rect width="48" height="48" rx="10" fill="#0866FF"/><path fill="#FFF" d="M28.4 47.9V29.5h6.2l.9-7.2h-7.1v-4.6c0-2.1.6-3.5 3.6-3.5h3.8V7.8c-.7-.1-3-.3-5.7-.3-5.7 0-9.6 3.5-9.6 9.9v4.9H14v7.2h6.5v18.4z"/></svg>;
  if (provider === 'instagram') return <svg viewBox="0 0 48 48" aria-hidden="true" focusable="false"><defs><linearGradient id="pruvs-instagram-grad" x1="0%" y1="100%" x2="100%" y2="0%"><stop offset="0%" stopColor="#FEDA75"/><stop offset="35%" stopColor="#FA7E1E"/><stop offset="65%" stopColor="#D62976"/><stop offset="100%" stopColor="#4F5BD5"/></linearGradient></defs><rect width="48" height="48" rx="12" fill="url(#pruvs-instagram-grad)"/><rect x="10.5" y="10.5" width="27" height="27" rx="8" fill="none" stroke="#fff" strokeWidth="3.3"/><circle cx="24" cy="24" r="6.5" fill="none" stroke="#fff" strokeWidth="3.3"/><circle cx="32.5" cy="15.5" r="2.2" fill="#fff"/></svg>;
  if (provider === 'tiktok') return <svg viewBox="0 0 48 48" aria-hidden="true" focusable="false"><rect width="48" height="48" rx="10" fill="#111"/><path d="M29 8v20.7a8.2 8.2 0 1 1-7.8-8.2v5a3.4 3.4 0 1 0 2.8 3.4V8zm0 0c.7 4.9 3.4 7.6 8.4 8v5.6c-4.1-.1-6.6-1.7-8.4-3.5" stroke="#25F4EE" strokeWidth="3.1" fill="none" transform="translate(-1.6,1)"/><path d="M29 8v20.7a8.2 8.2 0 1 1-7.8-8.2v5a3.4 3.4 0 1 0 2.8 3.4V8zm0 0c.7 4.9 3.4 7.6 8.4 8v5.6c-4.1-.1-6.6-1.7-8.4-3.5" stroke="#FE2C55" strokeWidth="3.1" fill="none" transform="translate(1.2,-.7)"/><path d="M29 8v20.7a8.2 8.2 0 1 1-7.8-8.2v5a3.4 3.4 0 1 0 2.8 3.4V8zm0 0c.7 4.9 3.4 7.6 8.4 8v5.6c-4.1-.1-6.6-1.7-8.4-3.5" stroke="white" strokeWidth="3.1" fill="none"/></svg>;
  return null;
}

export default function LoginMethodGrid({ enabledProviders = {}, onChoose, disabled = false }) {
  return <div className="auth-methods">
    <div className="auth-method-grid" role="group" aria-label="Choose how to sign in">
      {LOGIN_METHODS.map(method => {
        const available = method.id === 'email' || enabledProviders?.[method.id] === true;
        return <button
          key={method.id}
          type="button"
          className={'auth-method-tile' + (method.id === 'email' ? ' auth-method-tile--selected' : '')}
          aria-label={method.label + (available ? '' : ' — setup required')}
          aria-disabled={!available || disabled}
          disabled={!available || disabled}
          title={available ? 'Sign in with ' + method.label : method.label + ' sign-in is not configured'}
          onClick={() => onChoose(method.id)}
        ><span className="auth-method-icon"><BrandMark provider={method.id}/></span><span className="auth-method-label">{method.label}</span></button>;
      })}
    </div>
    <p className="auth-methods-note">Social sign-in options become available only after their secure provider connection is configured. Email and passkey sign-in remain available.</p>
  </div>;
}
