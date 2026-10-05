import json

from nicegui import ui

from app.db.database import SessionLocal
from app.i18n import t
from app.services.browser_upload_token_service import create_browser_upload_token
from app.ui.app_shell import app_header, bottom_nav, setup_page_head
from app.ui.auth_state import get_logged_in_user, require_login


def setup_upload_ui() -> None:
    @ui.page("/upload")
    def upload_page():
        user_id = require_login("/upload")
        if user_id is None:
            return

        db_user = SessionLocal()
        try:
            user = get_logged_in_user(db_user)
            lang = (user.preferred_language if user else "en") or "en"
        finally:
            db_user.close()

        upload_token = create_browser_upload_token(user_id)
        ro = lang == "ro"
        messages = {
            "choose": "Alege fotografie sau PDF" if ro else "Choose photo or PDF",
            "hint": "JPG, PNG, WEBP sau PDF · maximum 10 MB" if ro else "JPG, PNG, WEBP or PDF · up to 10 MB",
            "nothing_sent": (
                "Nimic nu este trimis către OCR până când confirmi imaginea finală."
                if ro else
                "Nothing is sent to OCR until you confirm the final image."
            ),
            "image_loaded": (
                "Imagine încărcată. Ajustează cadrul și trimite versiunea finală."
                if ro else
                "Image loaded. Adjust the frame, then send the final version."
            ),
            "pdf_loaded": (
                "PDF încărcat. Verifică documentul și trimite-l la OCR."
                if ro else
                "PDF loaded. Review it before sending to OCR."
            ),
            "invalid_type": (
                "Alege o imagine JPG, PNG, WEBP sau un PDF."
                if ro else
                "Choose a JPG, PNG, WEBP image or PDF."
            ),
            "too_large": (
                "Fișierul este prea mare. Limita este 10 MB."
                if ro else
                "The file is too large. Maximum size is 10 MB."
            ),
            "preparing": "Se pregătește imaginea…" if ro else "Preparing final image…",
            "uploading": "Se încarcă bonul în siguranță…" if ro else "Uploading receipt securely…",
            "reading": "Se citește bonul…" if ro else "Reading receipt…",
            "processed": "Bon procesat." if ro else "Receipt processed.",
            "select_first": "Alege mai întâi un bon." if ro else "Choose a receipt first.",
            "crop_failed": (
                "Imaginea decupată nu a putut fi pregătită."
                if ro else
                "The cropped image could not be prepared."
            ),
            "network_error": (
                "Încărcarea nu a reușit. Verifică conexiunea și încearcă din nou."
                if ro else
                "Upload failed. Check your connection and try again."
            ),
            "send": t("Send to OCR", lang),
            "crop_hint": (
                "Trage colțurile pentru decupare · deplasează imaginea pentru aliniere · cadrul luminos este exact zona trimisă la OCR"
                if ro else
                "Drag the corners to crop · move the image to align · the bright frame is exactly what will be sent to OCR"
            ),
        }

        config = {
            "token": upload_token,
            "endpoint": "/app/receipts/browser-upload",
            "maxBytes": 10 * 1024 * 1024,
            "maxDimension": 2400,
            "jpegQuality": 0.86,
            "messages": messages,
        }

        setup_page_head(f"{t('Scan receipt', lang)} · Pruvs")
        ui.add_head_html("""
<link href="https://cdn.jsdelivr.net/npm/cropperjs@1.6.2/dist/cropper.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/cropperjs@1.6.2/dist/cropper.min.js"></script>
<style>
.cropper-view-box,.cropper-face{border-radius:2px}.cropper-line{background-color:#1598ff}.cropper-point{background-color:#1598ff;width:9px;height:9px;border-radius:50%}.cropper-modal{background:#05070b;opacity:.72}.cropper-bg{background-image:none;background:#0a0d14}
.pruvs-browser-upload-zone{border:1.5px dashed #cbd5e1;border-radius:18px;background:#fbfcfd;padding:16px;width:100%}
.pruvs-browser-picker{display:inline-flex;align-items:center;gap:8px;min-height:44px;padding:0 16px;border:0;border-radius:12px;background:#0a1435;color:white;font-weight:700;cursor:pointer;user-select:none}
.pruvs-browser-picker:hover{background:#16234a}.pruvs-browser-picker:focus-within{outline:3px solid #8cb7ff;outline-offset:3px}
.pruvs-file-meta{font-size:12px;color:#61708b;margin-top:9px;word-break:break-word}
.pruvs-browser-panel{display:none;width:100%;margin-top:16px}
.pruvs-browser-toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;justify-content:center;padding:10px 2px 0}
.pruvs-browser-icon{width:40px;height:40px;border-radius:999px;border:1px solid #e5e7eb;background:#fff;color:#374151;display:inline-flex;align-items:center;justify-content:center;cursor:pointer}
.pruvs-browser-icon:hover{background:#f0f5ff;border-color:#b5cdf8}.pruvs-browser-icon:focus-visible{outline:3px solid #8cb7ff;outline-offset:2px}
.pruvs-browser-send-row{display:flex;justify-content:flex-end;margin-top:12px}
.pruvs-browser-send{display:inline-flex;align-items:center;gap:8px;min-height:44px;padding:0 18px;border:0;border-radius:12px;background:#0756df;color:#fff;font-weight:700;cursor:pointer}
.pruvs-browser-send:hover{background:#0649be}.pruvs-browser-send:disabled{opacity:.55;cursor:wait}
.pruvs-browser-status{font-size:12px;color:#61708b;margin-top:12px;min-height:18px}
.pruvs-progress-track{display:none;width:100%;height:6px;background:#e5e7eb;border-radius:999px;overflow:hidden;margin-top:10px}
.pruvs-progress-bar{height:100%;width:0;background:#0756df;border-radius:999px;transition:width .25s ease}
.pruvs-browser-note{font-size:11px;color:#94a3b8;margin-top:8px}
.pruvs-pdf-frame{width:100%;height:68vh;border:1px solid #e5e7eb;border-radius:16px;background:#fff}
</style>
""")
        ui.add_head_html(f"""
<script>
(() => {{
  const CONFIG = {json.dumps(config, ensure_ascii=False)};
  const state = {{ file: null, objectUrl: null, cropper: null, busy: false, initialized: false }};

  const byId = id => document.getElementById(id);
  const msg = key => (CONFIG.messages && CONFIG.messages[key]) || key;
  const setStatus = text => {{ const el = byId('pruvs-browser-status'); if (el) el.textContent = text || ''; }};
  const setProgress = value => {{
    const track = byId('pruvs-progress-track');
    const bar = byId('pruvs-progress-bar');
    if (!track || !bar) return;
    if (value === null) {{ track.style.display = 'none'; bar.style.width = '0%'; return; }}
    track.style.display = 'block';
    bar.style.width = `${{Math.max(0, Math.min(100, value))}}%`;
  }};
  const setBusy = busy => {{
    state.busy = busy;
    const buttons = document.querySelectorAll('[data-pruvs-upload-action]');
    buttons.forEach(button => button.disabled = !!busy);
    const input = byId('pruvs-file-input');
    if (input) input.disabled = !!busy;
  }};
  const humanSize = size => size < 1024 * 1024
    ? `${{Math.max(1, Math.round(size / 1024))}} KB`
    : `${{(size / (1024 * 1024)).toFixed(2)}} MB`;
  const isPdf = file => file && (file.type === 'application/pdf' || /\\.pdf$/i.test(file.name || ''));
  const isImage = file => file && ((file.type || '').startsWith('image/') || /\\.(jpe?g|png|webp)$/i.test(file.name || ''));

  const clearObjectUrl = () => {{
    if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
    state.objectUrl = null;
  }};

  const destroyCropper = () => {{
    if (state.cropper) {{ state.cropper.destroy(); state.cropper = null; }}
  }};

  const showPanel = name => {{
    const imagePanel = byId('pruvs-image-panel');
    const pdfPanel = byId('pruvs-pdf-panel');
    if (imagePanel) imagePanel.style.display = name === 'image' ? 'block' : 'none';
    if (pdfPanel) pdfPanel.style.display = name === 'pdf' ? 'block' : 'none';
  }};

  const loadSelectedFile = file => {{
    if (!file) return;
    if (file.size > CONFIG.maxBytes) {{
      setStatus(msg('too_large'));
      if (window.Quasar && Quasar.Notify) Quasar.Notify.create({{message: msg('too_large'), type: 'warning', position: 'top'}});
      const input = byId('pruvs-file-input'); if (input) input.value = '';
      return;
    }}
    if (!isImage(file) && !isPdf(file)) {{
      setStatus(msg('invalid_type'));
      if (window.Quasar && Quasar.Notify) Quasar.Notify.create({{message: msg('invalid_type'), type: 'warning', position: 'top'}});
      const input = byId('pruvs-file-input'); if (input) input.value = '';
      return;
    }}

    state.file = file;
    destroyCropper();
    clearObjectUrl();
    state.objectUrl = URL.createObjectURL(file);
    const meta = byId('pruvs-file-meta');
    if (meta) meta.textContent = `${{file.name || 'receipt'}} · ${{humanSize(file.size)}}`;
    setProgress(null);

    if (isPdf(file)) {{
      showPanel('pdf');
      const frame = byId('pruvs-pdf-preview');
      if (frame) frame.src = state.objectUrl;
      setStatus(msg('pdf_loaded'));
      return;
    }}

    showPanel('image');
    const image = byId('pruvs-crop-image');
    if (!image) return;
    image.onload = () => {{
      destroyCropper();
      if (typeof Cropper === 'undefined') {{
        setStatus('Cropper.js could not be loaded. Reload the page and try again.');
        return;
      }}
      state.cropper = new Cropper(image, {{
        viewMode: 1,
        dragMode: 'move',
        autoCropArea: 0.94,
        background: false,
        responsive: true,
        restore: true,
        guides: true,
        center: true,
        highlight: false,
        cropBoxMovable: true,
        cropBoxResizable: true,
        toggleDragModeOnDblclick: false,
      }});
    }};
    image.src = state.objectUrl;
    setStatus(msg('image_loaded'));
  }};

  const cropAction = action => {{
    const c = state.cropper;
    if (!c || state.busy) return;
    if (action === 'left') c.rotate(-90);
    if (action === 'right') c.rotate(90);
    if (action === 'zin') c.zoom(0.1);
    if (action === 'zout') c.zoom(-0.1);
    if (action === 'reset') c.reset();
  }};

  const croppedFile = async () => {{
    const original = state.file;
    if (!original || !isImage(original)) return original;
    if (!state.cropper) throw new Error(msg('crop_failed'));

    const canvas = state.cropper.getCroppedCanvas({{
      maxWidth: CONFIG.maxDimension,
      maxHeight: CONFIG.maxDimension,
      imageSmoothingEnabled: true,
      imageSmoothingQuality: 'high',
      fillColor: '#fff',
    }});
    if (!canvas) throw new Error(msg('crop_failed'));

    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', CONFIG.jpegQuality));
    if (!blob) throw new Error(msg('crop_failed'));
    if (blob.size > CONFIG.maxBytes) throw new Error(msg('too_large'));

    const sourceName = original.name || 'receipt.jpg';
    const stem = sourceName.replace(/\\.[^.]+$/, '') || 'receipt';
    return new File([blob], `${{stem}}-scan.jpg`, {{type: 'image/jpeg', lastModified: Date.now()}});
  }};

  const parseResponse = async response => {{
    const text = await response.text();
    if (!text) return {{}};
    try {{ return JSON.parse(text); }} catch (_) {{ return {{detail: text}}; }}
  }};

  const submit = async () => {{
    if (state.busy) return;
    if (!state.file) {{ setStatus(msg('select_first')); return; }}

    try {{
      setBusy(true);
      setProgress(15);
      setStatus(msg('preparing'));
      const prepared = await croppedFile();

      setProgress(38);
      setStatus(msg('uploading'));
      const form = new FormData();
      form.append('file', prepared, prepared.name || 'receipt');

      const response = await fetch(CONFIG.endpoint, {{
        method: 'POST',
        headers: {{'X-Pruvs-Upload-Token': CONFIG.token}},
        body: form,
        credentials: 'same-origin',
      }});

      setProgress(72);
      setStatus(msg('reading'));
      const result = await parseResponse(response);
      if (!response.ok) throw new Error(result.detail || `Upload failed (${{response.status}})`);
      if (!result.receipt_url) throw new Error('Receipt processing returned no receipt URL.');

      setProgress(100);
      setStatus(msg('processed'));
      if (window.Quasar && Quasar.Notify) Quasar.Notify.create({{message: msg('processed'), type: 'positive', position: 'top'}});
      window.location.assign(result.receipt_url);
    }} catch (error) {{
      setProgress(null);
      const message = (error && error.message) ? error.message : msg('network_error');
      setStatus(message);
      if (window.Quasar && Quasar.Notify) Quasar.Notify.create({{message, type: 'negative', position: 'top'}});
      setBusy(false);
    }}
  }};

  const init = () => {{
    const input = byId('pruvs-file-input');
    if (!input) {{ window.setTimeout(init, 100); return; }}
    if (state.initialized) return;
    state.initialized = true;
    input.addEventListener('change', event => loadSelectedFile(event.target.files && event.target.files[0]));
    window.addEventListener('beforeunload', clearObjectUrl, {{once: true}});
  }};

  window.pruvsReceiptUpload = {{ submit, cropAction }};
  window.setTimeout(init, 0);
}})();
</script>
""")

        with ui.element("main").classes("pruvio-page"):
            with ui.column().classes("pruvio-shell gap-4"):
                app_header("Scan receipt", language=lang)

                with ui.card().classes("pruvio-card w-full p-5 sm:p-7"):
                    with ui.row().classes("w-full items-start justify-between gap-4 flex-col sm:flex-row"):
                        with ui.column().classes("gap-1"):
                            ui.label(t("Receipt workspace", lang)).classes("text-2xl font-black tracking-tight text-slate-950")
                            ui.label(
                                "Fotografiază sau alege bonul. Îl poți alinia și decupa înainte ca imaginea finală să fie trimisă la OCR."
                                if ro else
                                "Take a photo or choose a receipt. Align and crop it first; only the final frame is sent to OCR."
                            ).classes("text-sm text-slate-500 max-w-2xl")
                        ui.icon("document_scanner").classes("text-3xl text-slate-300")

                    ui.html(f'''\n<div class="pruvs-browser-upload-zone" style="margin-top:16px">\n  <label class="pruvs-browser-picker" for="pruvs-file-input">\n    <span class="material-icons" aria-hidden="true">upload_file</span>\n    <span>{messages["choose"]}</span>\n    <input id="pruvs-file-input" type="file" accept="image/jpeg,image/png,image/webp,application/pdf" style="display:none">\n  </label>\n  <div class="pruvs-file-meta" id="pruvs-file-meta">{messages["hint"]}</div>\n</div>\n<div class="pruvs-browser-note">{messages["nothing_sent"]}</div>\n<div class="pruvs-browser-status" id="pruvs-browser-status"></div>\n<div class="pruvs-progress-track" id="pruvs-progress-track"><div class="pruvs-progress-bar" id="pruvs-progress-bar"></div></div>\n\n<div class="pruvs-browser-panel" id="pruvs-image-panel">\n  <div class="scan-frame">\n    <div class="scan-canvas"><img id="pruvs-crop-image" alt="Receipt editor"></div>\n    <div class="pruvs-browser-toolbar">\n      <button type="button" class="pruvs-browser-icon" data-pruvs-upload-action onclick="window.pruvsReceiptUpload.cropAction('left')" title="{t('Rotate left', lang)}"><span class="material-icons">rotate_left</span></button>\n      <button type="button" class="pruvs-browser-icon" data-pruvs-upload-action onclick="window.pruvsReceiptUpload.cropAction('right')" title="{t('Rotate right', lang)}"><span class="material-icons">rotate_right</span></button>\n      <button type="button" class="pruvs-browser-icon" data-pruvs-upload-action onclick="window.pruvsReceiptUpload.cropAction('zout')" title="{t('Zoom out', lang)}"><span class="material-icons">zoom_out</span></button>\n      <button type="button" class="pruvs-browser-icon" data-pruvs-upload-action onclick="window.pruvsReceiptUpload.cropAction('zin')" title="{t('Zoom in', lang)}"><span class="material-icons">zoom_in</span></button>\n      <button type="button" class="pruvs-browser-icon" data-pruvs-upload-action onclick="window.pruvsReceiptUpload.cropAction('reset')" title="{t('Reset image', lang)}"><span class="material-icons">restart_alt</span></button>\n    </div>\n    <div class="scan-hint">{messages["crop_hint"]}</div>\n  </div>\n  <div class="pruvs-browser-send-row">\n    <button type="button" class="pruvs-browser-send" data-pruvs-upload-action onclick="window.pruvsReceiptUpload.submit()"><span>{messages["send"]}</span><span class="material-icons">arrow_forward</span></button>\n  </div>\n</div>\n\n<div class="pruvs-browser-panel" id="pruvs-pdf-panel">\n  <iframe id="pruvs-pdf-preview" class="pruvs-pdf-frame" title="Receipt PDF preview"></iframe>\n  <div class="pruvs-browser-send-row">\n    <button type="button" class="pruvs-browser-send" data-pruvs-upload-action onclick="window.pruvsReceiptUpload.submit()"><span>{messages["send"]}</span><span class="material-icons">arrow_forward</span></button>\n  </div>\n</div>\n''', sanitize=False).classes("w-full")

        bottom_nav("upload", lang)
