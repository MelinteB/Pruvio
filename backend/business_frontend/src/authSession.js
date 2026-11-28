const SESSION_KEY = 'pruvs-business-session-v1';
const PAGE_KEY = 'pruvs-business-page-v1';

const ROUTES = new Set(['overview','stores','loyalty','claims','pilot','integrations','campaigns','promotions','customer-demo','team']);

export function restoreBusinessSession(storage = globalThis.sessionStorage) {
  try {
    const token = storage?.getItem(SESSION_KEY);
    return typeof token === 'string' ? token : '';
  } catch {
    return '';
  }
}

export function saveBusinessSession(token, storage = globalThis.sessionStorage) {
  const value = typeof token === 'string' ? token.trim() : '';
  try {
    if (value) storage?.setItem(SESSION_KEY, value);
    else storage?.removeItem(SESSION_KEY);
  } catch {
    // Keep the current page usable if browser storage is disabled. The user
    // will be asked to sign in again after a full reload in that case.
  }
  return value;
}

export function restoreBusinessPage(storage = globalThis.sessionStorage) {
  try {
    const page = storage?.getItem(PAGE_KEY);
    return ROUTES.has(page) ? page : 'overview';
  } catch {
    return 'overview';
  }
}

export function saveBusinessPage(page, storage = globalThis.sessionStorage) {
  const value = ROUTES.has(page) ? page : 'overview';
  try { storage?.setItem(PAGE_KEY, value); } catch {}
  return value;
}
