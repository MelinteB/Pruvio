import React from 'react';
import {
  ArrowRight,ArrowUpRight,BarChart3,Check,CheckCircle2,Clock3,
  Gift,MapPin,ReceiptText,ScanLine,ShieldCheck,Sparkles,Store,Target,UsersRound,
} from 'lucide-react';
import './merchant-overview-v0615.css';

/**
 * Operational command center. Every number comes from merchant-scoped API data;
 * no fake growth KPIs or paid-transfer claims. All actions navigate to real views.
 */
export default function MerchantOverview({
  merchantName='',stats,stores=[],programs=[],claims=[],onNavigate,onAddStore,onAddProgram,
}){
  const published=programs.filter(p=>p.status==='published');
  const completed=[
    stores.length>0,
    published.length>0,
    claims.some(c=>c.status==='approved'),
  ].filter(Boolean).length;
  const pending=Number(stats?.pending_claims??0);
  const cards=[
    {title:'Locations',value:stats?.stores??0,description:'Registered merchant locations',Icon:MapPin,to:'stores'},
    {title:'Loyalty programs',value:stats?.programs??0,description:published.length+' published',Icon:Gift,to:'loyalty'},
    {title:'Receipt reviews',value:pending,description:'Awaiting verification',Icon:ReceiptText,to:'claims'},
    {title:'Rewards redeemed',value:stats?.redeemed_rewards??0,description:'Recorded merchant redemptions',Icon:CheckCircle2,to:'integrations'},
  ];
  const steps=[
    {name:'Create your merchant location',detail:'Tell customers where rewards are earned',done:stores.length>0,onClick:()=>stores.length?onNavigate('stores'):onAddStore()},
    {name:'Publish a loyalty program',detail:'Define verified purchases and rewards',done:published.length>0,onClick:()=>programs.length?onNavigate('loyalty'):onAddProgram()},
    {name:'Verify your first receipt',detail:'Confirm qualifying purchases',done:claims.some(c=>c.status==='approved'),onClick:()=>onNavigate('claims')},
  ];
  return <div className="pruvs-biz-command">
    <section className="pruvs-biz-command-hero" aria-label="Merchant overview">
      <div className="pruvs-biz-command-copy">
        <div className="pruvs-biz-command-kicker"><span className="pruvs-biz-command-signal"/> YOUR BUSINESS · ALL IN ONE PLACE</div>
        <h2>Turn every great visit<br/><span>into the next one.</span></h2>
        <p>Welcome to {merchantName||'your merchant workspace'}. Build campaigns around real products, verify customer purchases and grow loyalty on your terms.</p>
        <div className="pruvs-biz-command-hero-actions">
          <button type="button" className="pruvs-biz-command-main-cta" onClick={()=>onNavigate('campaigns')}><Sparkles size={19}/> Open Campaign Studio <ArrowUpRight size={18}/></button>
          <button type="button" className="pruvs-biz-command-ghost" onClick={()=>onNavigate('claims')}><ScanLine size={18}/> Review receipts</button>
        </div>
        <div className="pruvs-biz-command-fine"><ShieldCheck size={15}/> Your campaigns are merchant-controlled. Nothing publishes automatically.</div>
      </div>
      <div className="pruvs-biz-command-art" aria-hidden="true">
        <div className="pruvs-biz-command-orbit orbit-a"/>
        <div className="pruvs-biz-command-orbit orbit-b"/>
        <div className="pruvs-biz-command-art-card">
          <div className="pruvs-biz-command-art-top"><img src="/business/business-favicon.svg" alt=""/><span>PRUVS BUSINESS</span><Sparkles size={17}/></div>
          <div className="pruvs-biz-command-art-visual"><span>YOUR NEXT CAMPAIGN</span><strong>Show what makes you memorable.</strong><div className="pruvs-biz-command-art-shape"/></div>
          <div className="pruvs-biz-command-art-bottom"><span className="pruvs-biz-command-art-pulse"/><b>From a picture to an offer</b><ArrowUpRight size={15}/></div>
        </div>
        <span className="pruvs-biz-command-floating"><Target size={16}/> Built for repeat visits</span>
      </div>
    </section>
    <div className="pruvs-biz-command-heading"><div><span className="pruvs-biz-overline">THE PULSE</span><h2>Your workspace at a glance</h2><p>Operational counts from your merchant account.</p></div><button type="button" onClick={()=>onNavigate('integrations')}>View integrations <ArrowUpRight size={16}/></button></div>
    <section className="pruvs-biz-command-kpis" aria-label="Merchant operating metrics">
      {cards.map(({title,value,description,Icon,to})=><button type="button" key={title} className="pruvs-biz-command-metric" onClick={()=>onNavigate(to)}>
        <span className="pruvs-biz-command-metric-top"><span>{title}</span><span className="pruvs-biz-command-metric-icon"><Icon size={21}/></span></span>
        <strong>{value}</strong><span className="pruvs-biz-command-metric-foot"><small>{description}</small><ArrowUpRight size={16}/></span>
      </button>)}
    </section>
    <div className="pruvs-biz-command-lower">
      <section className="pruvs-biz-setup">
        <div className="pruvs-biz-panel-head"><div><span className="pruvs-biz-overline">GET READY TO GROW</span><h2>Make the most of Pruvs</h2></div><span>{completed}/3 complete</span></div>
        <div className="pruvs-biz-setup-track" aria-label={completed+' of 3 onboarding steps complete'}><div style={{width:(completed/3*100)+'%'}}/></div>
        <div className="pruvs-biz-setup-steps">
          {steps.map((step,index)=><button type="button" key={step.name} onClick={step.onClick}>
            <span className={'pruvs-biz-setup-status '+(step.done?'done':'')}>{step.done?<Check size={18}/>:String(index+1).padStart(2,'0')}</span>
            <span className="pruvs-biz-setup-copy"><b>{step.name}</b><small>{step.detail}</small></span>
            <span className="pruvs-biz-setup-status-label">{step.done?'Complete':'Continue'} <ArrowRight size={15}/></span>
          </button>)}
        </div>
      </section>
      <section className="pruvs-biz-next-campaign">
        <span className="pruvs-biz-overline">CAMPAIGN ENGINE</span><div className="pruvs-biz-next-visual"><img src="/business/business-favicon.svg" alt=""/><span><Sparkles size={18}/></span></div>
        <h2>Real picture.<br/>Remarkable campaign.</h2>
        <p>Start with your product photograph, shape the message with AI and preview the offer exactly as customers will see it in Pruvs Core.</p>
        <button type="button" onClick={()=>onNavigate('campaigns')}>Create a campaign <ArrowUpRight size={17}/></button>
        <small>AI generation may incur provider charges. The merchant reviews every promotion.</small>
      </section>
    </div>
  </div>;
}
