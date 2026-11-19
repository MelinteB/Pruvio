import React, {useEffect, useId, useRef, useState} from 'react';
import {ChevronLeft, ChevronRight, Pause, Play} from 'lucide-react';
import {t} from './i18n';
import './campaign-carousel.css';

const MOTION_QUERY = '(prefers-reduced-motion: reduce)';
const ROTATION_DELAY = 8000;

export function livePromotions(promotions) {
  const byId = new Map();
  const now = Date.now();
  for (const promotion of promotions) {
    if (!promotion.id || !promotion.program_id || byId.has(promotion.id)) continue;
    if (promotion.status && promotion.status !== 'published') continue;
    if (promotion.expires_at && !(Date.parse(promotion.expires_at) > now)) continue;
    byId.set(promotion.id, promotion);
  }
  return [...byId.values()];
}

export default function CampaignCarousel({campaigns, label, initialCampaignId, renderCampaign}) {
  const region = useRef(null);
  const rotationOnPointerDown = useRef(null);
  const slidesId = useId();
  const [selectedId, setSelectedId] = useState(initialCampaignId);
  const [direction, setDirection] = useState('');
  const [paused, setPaused] = useState(Boolean(initialCampaignId));
  const [hovered, setHovered] = useState(false);
  const [visible, setVisible] = useState(() => !document.hidden);
  const [inView, setInView] = useState(() => typeof IntersectionObserver === 'undefined');
  const [reduceMotion, setReduceMotion] = useState(() => Boolean(window.matchMedia?.(MOTION_QUERY).matches));

  const count = campaigns.length;
  const index = Math.max(0, campaigns.findIndex(campaign => campaign.id === selectedId));
  const current = campaigns[index];
  const nextId = campaigns[(index + 1) % count]?.id;
  const rotating = count > 1 && !paused && !hovered && !reduceMotion && visible && inView;

  useEffect(() => {
    const update = () => setVisible(!document.hidden);
    document.addEventListener('visibilitychange', update);
    return () => document.removeEventListener('visibilitychange', update);
  }, []);

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting));
    observer.observe(region.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const preference = window.matchMedia?.(MOTION_QUERY);
    if (!preference) return;
    const update = () => setReduceMotion(preference.matches);
    if (preference.addEventListener) preference.addEventListener('change', update);
    else preference.addListener?.(update);
    return () => {
      if (preference.removeEventListener) preference.removeEventListener('change', update);
      else preference.removeListener?.(update);
    };
  }, []);

  useEffect(() => {
    if (!rotating) return;
    const timer = window.setTimeout(() => {
      setDirection('next');
      setSelectedId(nextId);
    }, ROTATION_DELAY);
    return () => window.clearTimeout(timer);
  }, [rotating, current?.id, nextId]);

  function move(offset) {
    setPaused(true);
    setDirection(offset > 0 ? 'next' : 'previous');
    setSelectedId(campaigns[(index + offset + count) % count].id);
  }

  return <div ref={region} className="campaign-carousel" role="region" aria-label={label}
    aria-roledescription={count > 1 ? t('carousel') : undefined}
    onFocusCapture={event => {
      if (!event.currentTarget.contains(event.relatedTarget)) setPaused(true);
    }}
    onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}>
    {count > 1 && <div className="campaign-carousel-controls">
      {!reduceMotion && <button type="button" aria-controls={slidesId}
        aria-label={t(paused ? 'Resume campaign rotation' : 'Pause campaign rotation')}
        onPointerDown={() => { rotationOnPointerDown.current = paused; }}
        onClick={event => {
          // Pointer focus can pause the carousel before this click is delivered.
          const previous = event.detail ? rotationOnPointerDown.current ?? paused : paused;
          rotationOnPointerDown.current = null;
          setPaused(!previous);
        }}>
        {paused ? <Play size={17} aria-hidden="true"/> : <Pause size={17} aria-hidden="true"/>}
      </button>}
      <button type="button" aria-controls={slidesId} aria-label={t('Previous campaign')} onClick={() => move(-1)}>
        <ChevronLeft size={20} aria-hidden="true"/>
      </button>
      <button type="button" aria-controls={slidesId} aria-label={t('Next campaign')} onClick={() => move(1)}>
        <ChevronRight size={20} aria-hidden="true"/>
      </button>
    </div>}
    <div className="campaign-carousel-viewport" id={slidesId} aria-live={rotating ? 'off' : 'polite'}>
      {current && <div className="campaign-carousel-slide" key={current.id} data-direction={direction}
        role={count > 1 ? 'group' : undefined} aria-roledescription={count > 1 ? t('slide') : undefined}
        aria-label={count > 1 ? t('{current} of {total}').replace('{current}', index + 1).replace('{total}', count) : undefined}>
        {renderCampaign(current)}
      </div>}
    </div>
  </div>;
}
