import test from 'node:test';
import assert from 'node:assert/strict';
import {restoreBusinessSession, saveBusinessSession, restoreBusinessPage, saveBusinessPage} from '../src/authSession.js';

function storage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: key => values.has(key) ? values.get(key) : null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: key => values.delete(key),
  };
}

test('restores a valid token from the current browser tab', () => {
  const store = storage({'pruvs-business-session-v1': 'token-123'});
  assert.equal(restoreBusinessSession(store), 'token-123');
});

test('persists a token and clears it on explicit logout or expiry', () => {
  const store = storage();
  assert.equal(saveBusinessSession(' token-123 ', store), 'token-123');
  assert.equal(restoreBusinessSession(store), 'token-123');
  assert.equal(saveBusinessSession('', store), '');
  assert.equal(restoreBusinessSession(store), '');
});

test('storage failures do not crash the login view', () => {
  const broken = {getItem(){throw Error('blocked')},setItem(){throw Error('blocked')},removeItem(){throw Error('blocked')}};
  assert.equal(restoreBusinessSession(broken), '');
  assert.equal(saveBusinessSession('token', broken), 'token');
});

test('restores a valid management section and rejects internal-only pages', () => {
  const store = storage();
  assert.equal(saveBusinessPage('promotions', store), 'promotions');
  assert.equal(restoreBusinessPage(store), 'promotions');
  assert.equal(saveBusinessPage('pilot-access', store), 'overview');
  assert.equal(restoreBusinessPage(store), 'overview');
});
