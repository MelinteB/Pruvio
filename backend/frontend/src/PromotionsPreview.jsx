import React,{useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {Megaphone,Gift} from 'lucide-react';
import {request} from './api';
import './promotions-preview.css';
/** Shows explicitly published, not-expired Business promotions; the parent gates this UI. */
export default function PromotionsPreview(){
  const [items,setItems]=useState([]);
  const [state,setState]=useState('loading');
  async function refresh(){
    setState('loading');
    try{
      const data=await request('/loyalty/promotions?limit=3');
      if(!Array.isArray(data))throw new Error('Invalid promotion response');
      setItems(data);setState('ready');
    }catch{
      // Service failure is not proof that merchants have no published campaigns.
      setState('unavailable');
    }
  }
  useEffect(()=>{refresh();},[]);
  if(state==='unavailable')return <section className="pruvs-promos" role="status">
    <p>Merchant campaigns are temporarily unavailable. Your rewards and receipts are unaffected.</p>
    <button type="button" onClick={refresh}>Retry campaigns</button>
  </section>;
  if(state==='loading'||!items.length)return null;
  return <section className="pruvs-promos" aria-label="Merchant loyalty promotions">
    <div className="pruvs-promos-heading"><div><Megaphone size={20}/><strong>Offers from participating businesses</strong></div><Link to="/rewards">Explore all rewards</Link></div>
    <div className="pruvs-promos-grid">{items.map(p=><article className="pruvs-promo" key={p.id}>
      {p.media_url && /^https:\/\//.test(p.media_url) && (p.media_type?.startsWith('image/') ? <img className="pruvs-v7149-promo-media" loading="lazy" src={p.media_url} alt={p.media_alt||p.headline}/> : p.media_type?.startsWith('video/') ? <video className="pruvs-v7149-promo-media" controls preload="none" muted playsInline aria-label={p.media_alt||p.headline}><source src={p.media_url} type={p.media_type}/></video> : null)} 
      <small className="pruvs-promo-tag">LOCAL REWARDS · {p.merchant_name}</small>
      <h3>{p.headline}</h3><p>{p.message}</p>
      <div className="pruvs-promo-meta"><Gift size={16}/>{p.stamps_required} qualifying receipts → {(p.reward_minor/100).toFixed(2)} {p.currency} reward</div>
      <Link to={'/rewards?program='+encodeURIComponent(p.program_id)}>See loyalty program</Link>
    </article>)}</div>
  </section>;
}
