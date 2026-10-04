"""Tab-scoped, short-lived form drafts and signed OTP workflow recovery.

Only explicitly listed non-secret fields are saved. A saved workflow is not
proof of verification: every action must still validate the OTP in the service.
"""
import base64
import hashlib
import hmac
import json
import os
import time

from nicegui import app, ui

TTL_SECONDS = 30 * 60


def _secret():
    value = os.getenv('PRUVIO_STORAGE_SECRET') or os.getenv('OTP_SECRET') or ''
    if len(value) < 32:
        raise ValueError('OTP recovery requires a server storage secret of at least 32 characters.')
    return value.encode()


def seal(scope, pending):
    data = json.dumps({'scope': scope, 'saved': time.time(), 'pending': pending}, separators=(',', ':')).encode()
    signature = hmac.new(_secret(), data, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signature + data).decode()


def unseal(scope, token):
    try:
        if not isinstance(token, str) or len(token) > 24000:
            return None
        raw = base64.urlsafe_b64decode(token)
        signature, data = raw[:32], raw[32:]
        if not hmac.compare_digest(signature, hmac.new(_secret(), data, hashlib.sha256).digest()):
            return None
        value = json.loads(data)
        if value['scope'] != scope or not 0 <= time.time() - value['saved'] <= TTL_SECONDS:
            return None
        return value
    except (ValueError, KeyError, TypeError):
        return None


class OTPRecovery:
    def __init__(self, scope, language='en'):
        self.scope = scope
        self.language = language
        self.fields = {}
        self.actions = {}
        self.pending = None
        self.tab_id = None
        self.key = 'pruvs:otp-recovery:v1:' + scope
        self.notice = ui.label('').classes('text-xs text-slate-500').props('role=status')

    def field(self, name, element):
        # Passwords and one-time-code fields must never be registered here.
        if element._props.get('type') == 'password' or element._props.get('autocomplete') in ('new-password', 'current-password', 'one-time-code'):
            raise ValueError('Secret fields cannot be persisted.')
        self.fields[name] = element

    def action(self, name, popup, state, keys, on_restore=None):
        self.actions[name] = (popup, state, tuple(keys), on_restore)
        popup.recovery = self
        popup.recovery_action = name

    def _fallback_key(self):
        return self.key + ':' + self.tab_id if self.tab_id else None

    def _persist(self, pending):
        self.pending = pending
        try:
            token = seal(self.scope, pending)
        except ValueError as error:
            self.notice.set_text(str(error))
            return
        fallback = self._fallback_key()
        if fallback:
            app.storage.user[fallback] = token
        # Keep the server copy first: if the socket drops here, the next page can recover it.
        ui.run_javascript(f'''(() => {{
          try {{ const key={json.dumps(self.key)};
            const value=JSON.parse(sessionStorage.getItem(key)||'{{}}');
            value.token={json.dumps(token)}; value.updated=Date.now();
            sessionStorage.setItem(key,JSON.stringify(value));
          }} catch (_) {{}}
        }})();''')

    def save(self, name, result):
        popup, state, keys, _ = self.actions[name]
        context = {key: state.get(key) for key in keys}
        # Never serialize result wholesale: it may contain debug OTP/password/user objects.
        display = {key: result.get(key) for key in ('destination', 'contact_type', 'requested_value')}
        self._persist({'action': name, 'context': context, 'display': display})

    def clear(self, clear_fields=False):
        self._persist(None)  # signed tombstone prevents stale pending-token resurrection
        if clear_fields:
            ui.run_javascript(f'''try {{ const key={json.dumps(self.key)};
              const value=JSON.parse(sessionStorage.getItem(key)||'{{}}'); value.fields={{}};
              sessionStorage.setItem(key,JSON.stringify(value)); }} catch (_) {{}}''')

    def start(self, after_restore=None):
        async def restore():
            configs = {name: {'id': element.id, 'boolean': isinstance(element.value, bool)} for name, element in self.fields.items()}
            try:
                result = await ui.run_javascript(f'''return (() => {{
                  const key={json.dumps(self.key)}, config={json.dumps(configs)};
                  try {{
                    const tabKey='pruvs:recovery-tab:v1';
                    let tab=sessionStorage.getItem(tabKey);
                    if(!tab){{tab=crypto.randomUUID();sessionStorage.setItem(tabKey,tab);}}
                    let value=JSON.parse(sessionStorage.getItem(key)||'{{}}');
                    if(!value.updated || Date.now()-value.updated>{TTL_SECONDS * 1000}) value={{}};
                    sessionStorage.setItem(key,JSON.stringify(value));
                    window.__pruvsDraftHandlers=window.__pruvsDraftHandlers||{{}};
                    if(window.__pruvsDraftHandlers[key]){{
                      document.removeEventListener('input',window.__pruvsDraftHandlers[key]);
                      document.removeEventListener('change',window.__pruvsDraftHandlers[key]);
                    }}
                    const save=(event)=>{{
                      for(const [name, field] of Object.entries(config)){{
                        const root=document.getElementById('c'+field.id);
                        if(!root || !root.contains(event.target)) continue;
                        const input=root.querySelector('input'); if(!input) continue;
                        const draft=JSON.parse(sessionStorage.getItem(key)||'{{}}');
                        draft.fields=draft.fields||{{}};
                        draft.fields[name]=field.boolean?input.checked:String(input.value).slice(0,500);
                        draft.updated=Date.now();sessionStorage.setItem(key,JSON.stringify(draft));
                      }}
                    }};
                    window.__pruvsDraftHandlers[key]=save;
                    document.addEventListener('input',save);document.addEventListener('change',save);
                    return {{tab, ...value}};
                  }} catch (_) {{return {{unavailable:true}};}}
                }})();''', timeout=10)
                if not isinstance(result, dict) or result.get('unavailable'):
                    self.notice.set_text('Draft recovery is unavailable in this browser. Keep this tab open.')
                    return
                tab = result.get('tab', '')
                if isinstance(tab, str) and len(tab) == 36:
                    self.tab_id = tab
                drafts = result.get('fields', {})
                for name, element in self.fields.items():
                    value = drafts.get(name) if isinstance(drafts, dict) else None
                    if isinstance(element.value, bool):
                        if isinstance(value, bool): element.set_value(value)
                    elif isinstance(value, str): element.set_value(value[:500])
                candidates = [unseal(self.scope, result.get('token'))]
                fallback = self._fallback_key()
                if fallback:
                    candidates.append(unseal(self.scope, app.storage.user.get(fallback)))
                valid = [value for value in candidates if value]
                latest = max(valid, key=lambda value: value['saved']) if valid else None
                if after_restore:
                    after_restore()
                pending = latest.get('pending') if latest else None
                if not isinstance(pending, dict) or pending.get('action') not in self.actions:
                    return
                name = pending['action']
                popup, state, keys, on_restore = self.actions[name]
                context = pending.get('context') or {}
                for key in keys:
                    state[key] = context.get(key)
                if not state.get('challenge_id'):
                    return
                if on_restore:
                    on_restore()
                self.pending = pending
                popup.present({**pending['display'], 'delivery': {'sent': True}}, recovering=True)
                self.notice.set_text('Verificare reluată. Dacă a expirat codul, folosește Retrimite.' if self.language == 'ro' else 'Verification restored. If the code has expired, use Resend code.')
            except Exception:
                self.notice.set_text('Nu am putut restaura formularul. Reîncarcă pagina după reconectare.' if self.language == 'ro' else 'Could not restore the form. Reload after reconnecting.')
        self.timer = ui.timer(0.2, restore, once=True)
