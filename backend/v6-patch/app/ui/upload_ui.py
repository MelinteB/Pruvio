import base64
import inspect
import json

from nicegui import ui

from app.db.database import SessionLocal
from app.i18n import t
from app.services.standalone_app_service import create_standalone_receipt_case
from app.ui.app_shell import app_header, bottom_nav, setup_page_head
from app.ui.auth_state import get_logged_in_user, require_login


async def _read_upload_event(event) -> tuple[bytes, str, str | None]:
    filename = getattr(event, "name", None)
    mime_type = getattr(event, "type", None)
    content = getattr(event, "content", None)
    if content is not None and hasattr(content, "read"):
        data = content.read()
        if inspect.isawaitable(data):
            data = await data
        return bytes(data), filename or "receipt.jpg", mime_type
    file_obj = getattr(event, "file", None)
    if file_obj is not None:
        filename = filename or getattr(file_obj, "name", None)
        mime_type = mime_type or getattr(file_obj, "content_type", None) or getattr(file_obj, "type", None)
        data = file_obj.read()
        if inspect.isawaitable(data):
            data = await data
        return bytes(data), filename or "receipt.jpg", mime_type
    raise ValueError("Could not read the uploaded file.")


def _data_uri(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _is_image(mime: str | None, filename: str | None) -> bool:
    return (mime or "").startswith("image/") or (filename or "").lower().endswith((".jpg", ".jpeg", ".png", ".webp"))


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

        setup_page_head(f"{t('Scan receipt', lang)} · Pruvio")
        ui.add_head_html("""
<link href="https://cdn.jsdelivr.net/npm/cropperjs@1.6.2/dist/cropper.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/cropperjs@1.6.2/dist/cropper.min.js"></script>
<style>
.cropper-view-box,.cropper-face{border-radius:2px}.cropper-line{background-color:#34d399}.cropper-point{background-color:#34d399;width:9px;height:9px;border-radius:50%}.cropper-modal{background:#05070b;opacity:.72}.cropper-bg{background-image:none;background:#0a0d14}
</style>
<script>
window.pruvioCropper = null;
window.pruvioCropperLoad = (src) => {
  const img = document.getElementById('pruvio-crop-image');
  if (!img) return;
  if (window.pruvioCropper) { window.pruvioCropper.destroy(); window.pruvioCropper = null; }
  img.src = src;
  img.onload = () => {
    window.pruvioCropper = new Cropper(img, {
      viewMode: 1, dragMode: 'move', autoCropArea: 0.94, background: false,
      responsive: true, restore: true, guides: true, center: true,
      highlight: false, cropBoxMovable: true, cropBoxResizable: true,
      toggleDragModeOnDblclick: false
    });
  };
};
window.pruvioCropperAction = (action) => {
  const c = window.pruvioCropper; if (!c) return;
  if (action === 'left') c.rotate(-90);
  if (action === 'right') c.rotate(90);
  if (action === 'zin') c.zoom(0.1);
  if (action === 'zout') c.zoom(-0.1);
  if (action === 'reset') c.reset();
};
window.pruvioCroppedReceipt = async () => {
  const c = window.pruvioCropper; if (!c) return null;
  const canvas = c.getCroppedCanvas({maxWidth:4096,maxHeight:4096,imageSmoothingEnabled:true,imageSmoothingQuality:'high',fillColor:'#fff'});
  return canvas ? canvas.toDataURL('image/jpeg',0.93) : null;
};
</script>""")

        state = {"original": None, "filename": None, "mime_type": None}

        with ui.element("main").classes("pruvio-page"):
            with ui.column().classes("pruvio-shell gap-4"):
                app_header("Scan receipt", language=lang)

                with ui.card().classes("pruvio-card w-full p-5 sm:p-7"):
                    with ui.row().classes("w-full items-start justify-between gap-4 flex-col sm:flex-row"):
                        with ui.column().classes("gap-1"):
                            ui.label(t("Receipt workspace", lang)).classes("text-2xl font-black tracking-tight text-slate-950")
                            ui.label(
                                "Fotografiază sau alege bonul. Îl poți alinia și decupa înainte ca imaginea finală să fie trimisă la OCR."
                                if lang == "ro" else
                                "Take a photo or choose a receipt. Align and crop it first; only the final frame is sent to OCR."
                            ).classes("text-sm text-slate-500 max-w-2xl")
                        ui.icon("document_scanner").classes("text-3xl text-slate-300")

                    status = ui.label("").classes("text-xs text-slate-500 mt-2")
                    progress = ui.linear_progress(value=0).classes("w-full mt-2")
                    progress.visible = False

                    editor = ui.column().classes("w-full gap-3 mt-4")
                    editor.visible = False
                    with editor:
                        with ui.element("div").classes("scan-frame w-full"):
                            ui.html('<div class="scan-canvas"><img id="pruvio-crop-image" alt="Receipt editor"></div>', sanitize=False).classes("w-full")
                            with ui.row().classes("scan-toolbar"):
                                for icon, title, action in [
                                    ("rotate_left", t("Rotate left", lang), "left"),
                                    ("rotate_right", t("Rotate right", lang), "right"),
                                    ("zoom_out", t("Zoom out", lang), "zout"),
                                    ("zoom_in", t("Zoom in", lang), "zin"),
                                    ("restart_alt", t("Reset image", lang), "reset"),
                                ]:
                                    ui.button(icon=icon, on_click=lambda action=action: ui.run_javascript(f"window.pruvioCropperAction('{action}')")).props(
                                        f"flat round dense title={json.dumps(title)} aria-label={json.dumps(title)}"
                                    ).classes("pruvio-icon-button")
                            ui.label(
                                "Trage colțurile pentru decupare · deplasează imaginea pentru aliniere · cadrul luminos este exact zona trimisă la OCR"
                                if lang == "ro" else
                                "Drag the corners to crop · move the image to align · the bright frame is exactly what will be sent to OCR"
                            ).classes("scan-hint")

                        async def send_to_ocr():
                            if not state["original"]:
                                return
                            progress.visible = True
                            progress.set_value(.25)
                            status.set_text("Se pregătește imaginea…" if lang == "ro" else "Preparing final image…")
                            payload = state["original"]
                            mime = state["mime_type"] or "application/octet-stream"
                            filename = state["filename"] or "receipt.jpg"
                            if _is_image(mime, filename):
                                try:
                                    data_uri = await ui.run_javascript("return await window.pruvioCroppedReceipt();", timeout=25.0)
                                    if data_uri and ',' in data_uri:
                                        payload = base64.b64decode(data_uri.split(',', 1)[1])
                                        mime = "image/jpeg"
                                        stem = filename.rsplit('.', 1)[0]
                                        filename = f"{stem}-scan.jpg"
                                except Exception as error:
                                    progress.visible = False
                                    status.set_text(str(error))
                                    ui.notify(str(error), type="negative")
                                    return
                            progress.set_value(.45)
                            status.set_text("Se citește bonul…" if lang == "ro" else "Reading receipt…")
                            try:
                                db = SessionLocal()
                                try:
                                    result = create_standalone_receipt_case(
                                        db=db, file_bytes=payload, original_filename=filename,
                                        mime_type=mime, user_id=user_id,
                                    )
                                    case_id = result["case"].id
                                finally:
                                    db.close()
                                progress.set_value(1)
                                ui.notify("Bon procesat." if lang == "ro" else "Receipt processed.", type="positive", position="top")
                                ui.navigate.to(f"/receipt/{case_id}")
                            except Exception as error:
                                progress.visible = False
                                status.set_text(str(error))
                                ui.notify(str(error), type="negative", position="top")

                        ui.button(t("Send to OCR", lang), icon="arrow_forward", on_click=send_to_ocr).classes("pruvio-primary self-end px-5")

                    pdf_panel = ui.column().classes("w-full gap-3 mt-4")
                    pdf_panel.visible = False
                    with pdf_panel:
                        pdf_preview = ui.html("").classes("w-full")
                        async def send_pdf():
                            progress.visible = True
                            progress.set_value(.4)
                            try:
                                db = SessionLocal()
                                try:
                                    result = create_standalone_receipt_case(
                                        db=db, file_bytes=state["original"], original_filename=state["filename"],
                                        mime_type=state["mime_type"], user_id=user_id,
                                    )
                                    case_id = result["case"].id
                                finally:
                                    db.close()
                                ui.navigate.to(f"/receipt/{case_id}")
                            except Exception as error:
                                progress.visible = False
                                ui.notify(str(error), type="negative")
                        ui.button(t("Send to OCR", lang), icon="arrow_forward", on_click=send_pdf).classes("pruvio-primary self-end px-5")

                    async def on_upload(event):
                        try:
                            data, filename, mime = await _read_upload_event(event)
                            state.update(original=data, filename=filename, mime_type=mime)
                            progress.visible = False
                            if _is_image(mime, filename):
                                pdf_panel.visible = False
                                editor.visible = True
                                source = _data_uri(data, mime or "image/jpeg")
                                ui.timer(.12, lambda: ui.run_javascript(f"window.pruvioCropperLoad({json.dumps(source)})"), once=True)
                                status.set_text("Imagine încărcată. Ajustează cadrul și trimite versiunea finală." if lang == "ro" else "Image loaded. Adjust the frame, then send the final version.")
                            else:
                                editor.visible = False
                                pdf_panel.visible = True
                                encoded = base64.b64encode(data).decode('ascii')
                                pdf_preview.set_content(f'<iframe src="data:application/pdf;base64,{encoded}" style="width:100%;height:68vh;border:1px solid #e5e7eb;border-radius:16px;background:white"></iframe>')
                                status.set_text("PDF încărcat. Verifică documentul și trimite-l la OCR." if lang == "ro" else "PDF loaded. Review it before sending to OCR.")
                        except Exception as error:
                            status.set_text(str(error))

                    with ui.element("div").classes("pruvio-upload-zone w-full mt-4"):
                        ui.upload(
                            label=("Fotografiază sau alege un bon" if lang == "ro" else "Take photo or choose receipt"),
                            on_upload=on_upload, auto_upload=True, max_file_size=10 * 1024 * 1024,
                        ).props('accept="image/jpeg,image/png,image/webp,application/pdf" color="dark" bordered flat hide-upload-btn').classes("w-full")
                    ui.label(
                        "Nimic nu este trimis către OCR până când confirmi imaginea finală."
                        if lang == "ro" else "Nothing is sent to OCR until you confirm the final image."
                    ).classes("text-[11px] text-slate-400 mt-2")

        bottom_nav("upload", lang)
