import React, {useEffect, useRef, useState} from 'react';
import {ChevronLeft, ChevronRight} from 'lucide-react';
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
  const remainingDelay = useRef(ROTATION_DELAY);
  const pointerStartX = useRef(null);
  const [selectedId, setSelectedId] = useState(initialCampaignId);
  const [direction, setDirection] = useState('next');
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [touching, setTouching] = useState(false);
  const [visible, setVisible] = useState(() => !document.hidden);
  const [inView, setInView] = useState(() => typeof IntersectionObserver === 'undefined');
  const [visibleCount, setVisibleCount] = useState(1);
  const [reduceMotion, setReduceMotion] = useState(() => Boolean(window.matchMedia?.(MOTION_QUERY).matches));

  const count = campaigns.length;
  const index = Math.max(0, campaigns.findIndex(campaign => campaign.id === selectedId));
  const current = campaigns[index];
  const nextId = campaigns[(index + 1) % count]?.id;
  const shownCount = Math.min(visibleCount, count);
  const visibleCampaigns = Array.from({length: shownCount}, (_, offset) => campaigns[(index + offset) % count]);
  const pausedByInteraction = hovered || focused || touching;
  const rotationAvailable = count > shownCount && !reduceMotion && visible && inView;
  const rotating = rotationAvailable && !pausedByInteraction;

  const move = offset => {
    if (count <= shownCount) return;
    remainingDelay.current = ROTATION_DELAY;
    setDirection(offset > 0 ? 'next' : 'previous');
    setSelectedId(campaigns[(index + offset + count) % count].id);
  };

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
    const update = width => setVisibleCount(width >= 980 ? 3 : width >= 560 ? 2 : 1);
    const measure = () => update(region.current?.getBoundingClientRect().width || window.innerWidth);
    measure();
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure);
      return () => window.removeEventListener('resize', measure);
    }
    const observer = new ResizeObserver(([entry]) => update(entry.contentRect.width));
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
    const startedAt = Date.now();
    let completed = false;
    const timer = window.setTimeout(() => {
      completed = true;
      remainingDelay.current = ROTATION_DELAY;
      setDirection('next');
      setSelectedId(nextId);
    }, remainingDelay.current);
    return () => {
      window.clearTimeout(timer);
      if (!completed) remainingDelay.current = Math.max(0, remainingDelay.current - (Date.now() - startedAt));
    };
  }, [rotating, current?.id, nextId]);

  return <div ref={region} className="campaign-carousel" role="region" aria-label={label}
    aria-roledescription={count > 1 ? t('carousel') : undefined}
    onFocusCapture={event => {
      if (!event.currentTarget.contains(event.relatedTarget)) setFocused(true);
    }}
    onBlurCapture={event => {
      if (!event.currentTarget.contains(event.relatedTarget)) setFocused(false);
    }}
    onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}>
    <div className="campaign-carousel-touch-area"
      onPointerDown={event => {
        if (event.pointerType !== 'touch') return;
        pointerStartX.current = event.clientX;
        setTouching(true);
      }}
      onPointerUp={event => {
        if (event.pointerType !== 'touch') return;
        const startX = pointerStartX.current;
        pointerStartX.current = null;
        setTouching(false);
        if (startX === null) return;
        const distance = event.clientX - startX;
        if (Math.abs(distance) >= 40) move(distance < 0 ? 1 : -1);
      }}
      onPointerCancel={() => {
        pointerStartX.current = null;
        setTouching(false);
      }}>
    <div className="campaign-carousel-viewport" aria-live="off"
      style={{'--campaigns-visible': shownCount}}>
      {visibleCampaigns.map((campaign, offset) => <div className="campaign-carousel-slide" key={campaign.id} data-direction={direction}
        role={count > 1 ? 'group' : undefined} aria-roledescription={count > 1 ? t('slide') : undefined}
        aria-label={count > 1 ? t('{current} of {total}').replace('{current}', ((index + offset) % count) + 1).replace('{total}', count) : undefined}>
        {renderCampaign(campaign)}
      </div>)}
    </div>
    </div>
    {count > 1 && <div className="campaign-carousel-status">
      <div className="campaign-carousel-position" aria-hidden="true">
        <span>{index + 1} / {count}</span>
        <div className="campaign-carousel-progress"><i key={current?.id} data-active={rotationAvailable}
          data-paused={pausedByInteraction}/></div>
      </div>
      {count > shownCount && <div className="campaign-carousel-navigation">
        <button type="button" aria-label={t('Previous campaign')} onClick={event => {
          move(-1);
          if (event.detail) event.currentTarget.blur();
        }}><ChevronLeft size={18} aria-hidden="true"/></button>
        <button type="button" aria-label={t('Next campaign')} onClick={event => {
          move(1);
          if (event.detail) event.currentTarget.blur();
        }}><ChevronRight size={18} aria-hidden="true"/></button>
      </div>}
    </div>}
  </div>;
}
