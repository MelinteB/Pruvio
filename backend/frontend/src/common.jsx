import { t } from "./i18n";
import React, { createContext, useContext, useState, useEffect, useId } from 'react';
import { LoaderCircle, AlertCircle, CheckCircle2 } from 'lucide-react';
export const Context = createContext(null);
export const useApp = () => useContext(Context);
export function useLoad(loader, deps = []) {
  const [data, setData] = useState(null),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(true);
  async function reload() {
    setError('');
    try {
      setData(await loader());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    loader().then(d => active && setData(d)).catch(e => active && setError(e.message)).finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, deps);
  return {
    data,
    setData,
    error,
    loading,
    reload
  };
}
export function Message({
  error,
  children
}) {
  return <div role={error ? 'alert' : 'status'} className={'message ' + (error ? 'error' : 'success')}>{error ? <AlertCircle size={18} /> : <CheckCircle2 size={18} />}<span>{children || error}</span></div>;
}
export function Spinner() {
  return <div className="loading"><LoaderCircle className="spin" /> {t("Loading…")}</div>;
}
export function Field({
  label,
  children,
  ...props
}) {
  const generated = useId(),
    id = props.id || generated;
  return <div className="field"><label htmlFor={id}>{label}</label>{children ? React.cloneElement(children, {
      id
    }) : <input {...props} id={id} />}</div>;
}
export function Check({
  label,
  ...props
}) {
  return <label className="check"><input type="checkbox" {...props} /><span>{label}</span></label>;
}
export function Badge({
  children
}) {
  return <span className={'badge ' + (children === 'open' ? 'blue' : children === 'settled' || children === 'active' ? 'green' : '')}>{children}</span>;
}
export function Title({
  eyebrow,
  title,
  children,
  action
}) {
  return <div className="page-title"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1>{children && <p>{children}</p>}</div>{action}</div>;
}
export function Panel({
  title,
  children,
  className = ''
}) {
  return <section className={'panel ' + className}>{title && <h2>{title}</h2>}{children}</section>;
}
export function Action({
  onClick,
  children,
  className = '',
  ...props
}) {
  const [busy, setBusy] = useState(false);
  return <button {...props} disabled={props.disabled || busy} className={className} onClick={async e => {
    if (busy) return;
    setBusy(true);
    try {
      await onClick?.(e);
    } finally {
      setBusy(false);
    }
  }}>{busy ? <LoaderCircle size={17} className="spin" /> : null}{children}</button>;
}
export function Empty({
  children
}) {
  return <div className="empty">{children}</div>;
}
