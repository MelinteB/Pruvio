import React from 'react';
import './social-auth-options.css';

const METHODS = [
  {id:'google',name:'Google',mark:'G',hint:'Google Account'},
  {id:'apple',name:'Apple',mark:'A',hint:'Apple Account (iPhone, iPad, Mac)'},
  {id:'facebook',name:'Facebook',mark:'f',hint:'Facebook account'},
  {id:'yahoo',name:'Yahoo',mark:'Y',hint:'Yahoo account'},
  {id:'tiktok',name:'TikTok',mark:'T',hint:'TikTok account'},
  {id:'instagram',name:'Instagram Professional',mark:'IG',hint:'Business and Creator accounts only'}
];
const MODE_TEXT = {login:'Continue with',register:'Sign up with',link:'Connect'};
function internalPath(value) {
  return typeof value==='string' && value.startsWith('/') && !value.startsWith('//')
    && !value.includes('\\') ? value : '/';
}
export default function SocialAuthOptions({
  providers=[], loading=false, mode='login', next='/', linked=[]
}) {
  const byId=new Map((providers||[]).map(p=>[p.id,p]));
  const existing=new Set(linked);
  const available=METHODS.filter(p=>!existing.has(p.id));
  if(!available.length) return null;
  return <section className="pruvs-social-auth" aria-label="Additional sign-in methods">
    <div className="pruvs-social-auth-title">
      <span>{mode==='link'?'Connect another account':
        mode==='register'?'Or sign up using':'Or sign in using'}</span>
    </div>
    <div className="pruvs-social-auth-grid">
      {available.map(provider=>{
        const info=byId.get(provider.id);
        const ready=info?.enabled===true;
        const label=MODE_TEXT[mode]+' '+provider.name;
        const url='/api/v1/auth/social/'+encodeURIComponent(provider.id)+'/start?mode='+
          encodeURIComponent(mode)+(mode==='link'?'':'&next='+encodeURIComponent(internalPath(next)));
        const content=<>
          <span className={'pruvs-social-symbol provider-'+provider.id} aria-hidden="true">{provider.mark}</span>
          <span className="pruvs-social-method-label"><strong>{label}</strong>
            <small>{ready?provider.hint:loading?'Checking availability…':'Setup required'}</small>
          </span>
          <span className={'pruvs-social-state '+(ready?'ready':'pending')}>
            {ready?'Available':'Unavailable'}
          </span>
        </>;
        return ready
          ? <a href={url} key={provider.id} className="pruvs-social-method">{content}</a>
          : <div key={provider.id} className="pruvs-social-method is-disabled" aria-disabled="true"
              title="Provider authorization has not been configured for this environment">{content}</div>;
      })}
    </div>
    <p className="pruvs-social-explainer">
      {mode==='link'?
        'Connect a provider while signed in. Your Pruvs account and receipts stay under your control.':
        'These providers require developer credentials and approval before they can be activated. You can still use email and password.'}
      {mode!=='link'&&' Existing accounts must link a provider in Account before using it to sign in.'}
    </p>
    {mode==='register'&&<p className="pruvs-social-explainer">
      Instagram Professional signup is available for Business or Creator accounts only and requires Pruvs email verification. Personal Instagram accounts cannot use this method.
    </p>}
  </section>;
}