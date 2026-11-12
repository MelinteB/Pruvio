'use strict';
// Pruvs Business v0.6.2: enrollment safety, field validation and same-tab resume.
// API hosts are deliberately explicit to avoid routing staging traffic to production.
const API_HOST_BY_UI_HOST = Object.freeze({
  'pruvs-business-ui-staging.onrender.com': 'https://pruvs-business-api-staging.onrender.com',
  'pruvs-business-api-staging.onrender.com': 'https://pruvs-business-api-staging.onrender.com',
  'pruvs-business-ui.onrender.com': 'https://pruvs-business-api.onrender.com',
});
const apiBase = location.pathname.startsWith('/business/') ? '/business' : (API_HOST_BY_UI_HOST[location.hostname] || null);
const pendingKey = 'pruvs-business-enrollment-pending'; // v0.6.1 compatibility
const draftKey = 'pruvs-business-enrollment-draft-v062';
const draftMaxAgeMs = 24 * 60 * 60 * 1000;
let currentStep = 1;
let pending = null;
let resendAvailableAt = 0;
const $ = selector => document.querySelector(selector);
const all = selector => [...document.querySelectorAll(selector)];
const enrollmentForm = $('#enrollment');

function localFeedback() {
  const section = $(`[data-step="${currentStep}"]`);
  if (!section) return null;
  let node = section.querySelector('[data-enroll-feedback]');
  if (!node) {
    node = document.createElement('div');
    node.setAttribute('data-enroll-feedback', '');
    node.className = 'notice';
    node.setAttribute('role', 'alert');
    node.setAttribute('aria-live', 'polite');
    node.hidden = true;
    const actions = section.querySelector('.actions');
    if (actions) section.insertBefore(node, actions);
    else section.appendChild(node);
  }
  return node;
}
function notice(message, success = false) {
  const top = $('#notice');
  top.textContent = message;
  top.classList.toggle('ok', success);
  top.hidden = !message;
  all('[data-enroll-feedback]').forEach(node => { node.hidden = true; node.textContent = ''; });
  const nearby = localFeedback();
  if (nearby) {
    nearby.textContent = message;
    nearby.classList.toggle('ok', success);
    nearby.hidden = !message;
  }
}
function go(step) {
  currentStep = step;
  all('[data-step]').forEach(n => { n.hidden = Number(n.dataset.step) !== step; });
  enrollmentForm.hidden = step > 3;
  $('#completed').hidden = step !== 5;
  all('[data-step-indicator]').forEach(node => {
    const number = Number(node.dataset.stepIndicator);
    node.classList.toggle('active', number === Math.min(step, 4));
    node.classList.toggle('done', number < step);
  });
  notice('');
  if (step <= 3 && !pending) saveDraft();
  window.scrollTo({top: 0, behavior: 'smooth'});
}
function inputLabel(node) {
  const label = node.closest('label');
  if (label) {
    const value = label.textContent.trim().replace(/\s+/g, ' ');
    if (value) return value.split('(')[0].trim();
  }
  return node.name || 'Field';
}
function validationReason(input) {
  if (input.name === 'password' && input.validity?.tooShort) {
    return 'Use at least 20 characters for your password.';
  }
  if (input.validity?.valueMissing) return `${inputLabel(input)} is required.`;
  if (input.validity?.typeMismatch) return `Please enter a valid ${inputLabel(input).toLowerCase()}.`;
  if (input.validity?.tooShort) return `${inputLabel(input)} is too short.`;
  if (input.validity?.tooLong) return `${inputLabel(input)} is too long.`;
  return input.validationMessage || `Please correct ${inputLabel(input)}.`;
}
function validateStep(step) {
  const section = $(`[data-step="${step}"]`);
  if (!section) return false;
  const inputs = all(`[data-step="${step}"] input, [data-step="${step}"] select`);
  for (const input of inputs) {
    if (input.disabled || input.checkValidity()) {
      input.removeAttribute('aria-invalid');
      continue;
    }
    // Critical fix: reveal the step BEFORE focusing its invalid input.
    // In v0.6.1, previous hidden steps were validated invisibly.
    if (currentStep !== step) go(step);
    input.setAttribute('aria-invalid', 'true');
    notice(validationReason(input));
    input.focus();
    return false;
  }
  return true;
}
function readableApiError(response, payload) {
  let field = null;
  let message = '';
  if (Array.isArray(payload.detail)) {
    const issue = payload.detail[0];
    field = Array.isArray(issue?.loc) ? issue.loc[issue.loc.length - 1] : null;
    const element = field ? enrollmentForm.elements.namedItem(field) : null;
    const label = element ? inputLabel(element) : (field || 'Registration details');
    message = `${label}: ${issue?.msg || 'invalid value'}`;
  } else if (typeof payload.detail === 'string') {
    message = payload.detail;
  }
  if (response.status === 404 && !message) message = 'Merchant enrollment is not enabled on this environment.';
  if (response.status === 503 && !message) message = 'The verification email service is temporarily unavailable.';
  if (response.status === 409 && !message) message = 'An application already exists for this email. Resume in the original browser tab.';
  return {field, message: message || `Registration request failed (HTTP ${response.status}).`};
}
async function post(path, body) {
  if (!apiBase) throw new Error('Merchant enrollment is not configured for this hostname.');
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), 20000);
  let response;
  try {
    response = await fetch(`${apiBase}/v1/merchant/enrollment${path}`, {
      method: 'POST', mode: 'cors', cache: 'no-store',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body), signal: abort.signal,
    });
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('The request timed out. Check your email before retrying; your registration may have been accepted.');
    }
    throw new Error('The Business API could not be reached. Check connectivity and CORS settings.');
  } finally { clearTimeout(timer); }
  let payload = {};
  try { payload = await response.json(); } catch { /* allow generic failure */ }
  if (!response.ok) {
    const error = readableApiError(response, payload);
    const failure = new Error(error.message);
    failure.field = error.field;
    failure.status = response.status;
    throw failure;
  }
  return payload;
}
function formData() {
  const fd = new FormData(enrollmentForm);
  const data = Object.fromEntries(fd.entries());
  for (const key of ['vat_registered', 'accept_terms', 'acknowledge_privacy', 'marketing_opt_in']) {
    data[key] = enrollmentForm.elements.namedItem(key).checked;
  }
  return data;
}
function saveDraft() {
  if (pending) return;
  const fields = {};
  for (const input of all('#enrollment input, #enrollment select')) {
    if (!input.name || input.name === 'password') continue;
    fields[input.name] = input.type === 'checkbox' ? !!input.checked : input.value;
  }
  try { sessionStorage.setItem(draftKey, JSON.stringify({at: Date.now(), step: Math.min(currentStep, 3), fields})); }
  catch { /* private browsing or storage blocked: continue without resume */ }
}
function clearDraft() { try { sessionStorage.removeItem(draftKey); } catch { /* optional */ } }
function restoreDraft() {
  try {
    const data = JSON.parse(sessionStorage.getItem(draftKey) || 'null');
    if (!data || !data.at || Date.now() - data.at > draftMaxAgeMs || !data.fields) return false;
    for (const [key, value] of Object.entries(data.fields)) {
      if (key === 'password') continue;
      const input = enrollmentForm.elements.namedItem(key);
      if (!input || input.type === 'password' || input.readOnly) continue;
      if (input.type === 'checkbox') input.checked = value === true;
      else input.value = String(value).slice(0, input.maxLength > 0 ? input.maxLength : 512);
    }
    go(Math.max(1, Math.min(3, Number(data.step) || 1)));
    notice('Your enrollment details were restored. For security, re-enter your password before requesting a code.', true);
    return true;
  } catch { return false; }
}
function savePending(next) {
  pending = next;
  sessionStorage.setItem(pendingKey, JSON.stringify(next));
  clearDraft();
}
function loadPending() {
  try {
    const result = JSON.parse(sessionStorage.getItem(pendingKey) || 'null');
    return result?.signup_id && result?.session_token ? result : null;
  } catch { return null; }
}
function updateTimer() {
  const left = Math.max(0, Math.ceil((resendAvailableAt - Date.now()) / 1000));
  $('#resend').disabled = Boolean(left);
  $('#countdown').textContent = left ? `(${left}s)` : '';
}
function enterCompleted() {
  $('#merchantId').textContent = pending?.merchant_id || 'Pending';
  go(5);
}
function enterVerify() {
  $('#maskedEmail').textContent = pending?.email_masked || 'your email';
  resendAvailableAt = pending?.resendAvailableAt || Date.now() + 60000;
  go(4);
  updateTimer();
}
function setBusy(button, busy) {
  button.disabled = busy;
  if (busy) {
    button.dataset.previousLabel = button.textContent;
    button.textContent = button.id === 'submitButton' ? 'Sending verification code…' : 'Processing…';
  } else if (button.dataset.previousLabel) {
    button.textContent = button.dataset.previousLabel;
    delete button.dataset.previousLabel;
  }
}
function showRequestError(error) {
  if (error.field) {
    const input = enrollmentForm.elements.namedItem(error.field);
    if (input) {
      const section = input.closest('[data-step]');
      if (section && currentStep !== Number(section.dataset.step)) go(Number(section.dataset.step));
      input.setAttribute('aria-invalid', 'true');
      input.focus();
    }
  }
  notice(error.message || 'An unexpected error occurred.');
}

all('[data-next]').forEach(button => button.addEventListener('click', () => {
  if (validateStep(currentStep)) go(currentStep + 1);
}));
all('[data-prev]').forEach(button => button.addEventListener('click', () => go(currentStep - 1)));
enrollmentForm.addEventListener('input', saveDraft);
enrollmentForm.addEventListener('change', saveDraft);
enrollmentForm.addEventListener('submit', async event => {
  event.preventDefault();
  for (const step of [1, 2, 3]) if (!validateStep(step)) return;
  const button = $('#submitButton');
  setBusy(button, true); notice('');
  try {
    const result = await post('/start', formData());
    savePending({...result, resendAvailableAt: Date.now() + 60000});
    enrollmentForm.elements.namedItem('password').value = '';
    enterVerify();
    notice('Verification code sent. Please check your inbox.', true);
  } catch (error) { showRequestError(error); }
  finally { setBusy(button, false); }
});
$('#verify').addEventListener('click', async () => {
  const code = $('#otpCode').value.trim();
  if (!/^\d{6}$/.test(code)) { notice('Enter the six-digit code from your email.'); return; }
  const button = $('#verify'); setBusy(button, true); notice('');
  try {
    const result = await post('/verify', {...pending, code});
    if (result.status !== 'pending_review') throw new Error('Unexpected verification state.');
    savePending({...pending, status: 'pending_review', merchant_id: result.merchant_id});
    enterCompleted();
  } catch (error) { notice(error.message); }
  finally { setBusy(button, false); }
});
$('#resend').addEventListener('click', async () => {
  const button = $('#resend'); setBusy(button, true); notice('');
  try {
    await post('/resend', pending);
    pending.resendAvailableAt = Date.now() + 60000;
    savePending(pending);
    resendAvailableAt = pending.resendAvailableAt;
    $('#otpCode').value = '';
    notice('A new code has been sent.', true);
  } catch (error) { notice(error.message); }
  finally { setBusy(button, false); updateTimer(); }
});
$('#startOver').addEventListener('click', async () => {
  if (pending) {
    try { await post('/cancel', pending); }
    catch (error) { notice(`Unable to cancel pending registration: ${error.message}`); return; }
  }
  sessionStorage.removeItem(pendingKey);
  pending = null;
  enrollmentForm.reset();
  clearDraft();
  go(1);
});
setInterval(updateTimer, 1000);
$('#checkStatus').addEventListener('click', async () => {
  try {
    const result = await post('/status', pending);
    if (result.status === 'approved') notice('Your merchant account is approved. You can sign in.', true);
    else notice('Your enrollment is still awaiting business review.', true);
  } catch (error) { notice(error.message); }
});
pending = loadPending();
if (pending?.status === 'pending_review') enterCompleted();
else if (pending) enterVerify();
else if (!restoreDraft()) go(1);
if (!apiBase) notice('Registration is unavailable: unknown deployment hostname.');
