import base64
import inspect

from nicegui import ui

from app.db.database import SessionLocal
from app.i18n import t
from app.services.image_edit_service import data_uri, edit_image, is_editable_image
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
        read_result = file_obj.read()
        if inspect.isawaitable(read_result):
            read_result = await read_result
        return bytes(read_result), filename or "receipt.jpg", mime_type

    raise ValueError("Could not read the uploaded file.")


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
        state = {
            "original": None,
            "edited": None,
            "filename": None,
            "mime_type": None,
            "rotation": 0,
        }

        with ui.element("main").classes("pruvio-page"):
            with ui.column().classes("pruvio-shell gap-4"):
                app_header("Scan receipt", language=lang)

                with ui.card().classes("pruvio-card w-full p-6 sm:p-8"):
                    ui.label(t("Add a receipt", lang)).classes("text-2xl sm:text-3xl font-black text-slate-950")
                    ui.label(
                        "Încarcă mai întâi imaginea, verific-o și decupeaz-o dacă este nevoie. OCR-ul pornește doar după ce apeși butonul Trimite la OCR."
                        if lang == "ro"
                        else "Load the image first, review and crop it if needed. OCR starts only after you press Send to OCR."
                    ).classes("text-sm text-slate-500 max-w-2xl")

                    progress = ui.linear_progress(value=0).classes("w-full mt-3")
                    progress.visible = False
                    status = ui.label("").classes("text-sm text-slate-500")

                    preview_panel = ui.column().classes("w-full gap-3 mt-4")
                    preview_panel.visible = False
                    with preview_panel:
                        ui.label(t("Preview & edit", lang)).classes("text-lg font-black text-slate-950")
                        image_preview = ui.image().classes(
                            "w-full max-h-[70vh] object-contain rounded-2xl border border-slate-200 bg-slate-50"
                        )
                        pdf_preview = ui.html("").classes("w-full")
                        pdf_preview.visible = False

                        controls = ui.column().classes("w-full gap-3")
                        with controls:
                            with ui.grid(columns=2).classes("w-full gap-3"):
                                crop_left = ui.slider(min=0, max=40, value=0, step=1).props(f'label-always label="{t("Crop left", lang)} %"')
                                crop_right = ui.slider(min=0, max=40, value=0, step=1).props(f'label-always label="{t("Crop right", lang)} %"')
                                crop_top = ui.slider(min=0, max=40, value=0, step=1).props(f'label-always label="{t("Crop top", lang)} %"')
                                crop_bottom = ui.slider(min=0, max=40, value=0, step=1).props(f'label-always label="{t("Crop bottom", lang)} %"')
                            scale = ui.slider(min=25, max=200, value=100, step=5).props(f'label-always label="{t("Scale", lang)} %"').classes("w-full")
                            with ui.row().classes("gap-2 flex-wrap"):
                                def rotate(delta: int):
                                    state["rotation"] = (int(state["rotation"]) + delta) % 360
                                    apply_preview()

                                ui.button(t("Rotate left", lang), icon="rotate_left", on_click=lambda: rotate(-90)).classes("pruvio-secondary")
                                ui.button(t("Rotate right", lang), icon="rotate_right", on_click=lambda: rotate(90)).classes("pruvio-secondary")

                                def reset_edit():
                                    crop_left.value = crop_right.value = crop_top.value = crop_bottom.value = 0
                                    scale.value = 100
                                    state["rotation"] = 0
                                    apply_preview()

                                ui.button(t("Reset edit", lang), icon="restart_alt", on_click=reset_edit).classes("pruvio-secondary")

                        def apply_preview():
                            if not state["original"] or not is_editable_image(state["mime_type"], state["filename"]):
                                return
                            try:
                                edited, edited_mime = edit_image(
                                    state["original"],
                                    crop_left_pct=float(crop_left.value or 0),
                                    crop_right_pct=float(crop_right.value or 0),
                                    crop_top_pct=float(crop_top.value or 0),
                                    crop_bottom_pct=float(crop_bottom.value or 0),
                                    scale_pct=float(scale.value or 100),
                                    rotation_degrees=int(state["rotation"]),
                                )
                            except Exception as error:
                                status.set_text(str(error))
                                return
                            state["edited"] = edited
                            state["edited_mime"] = edited_mime
                            image_preview.set_source(data_uri(edited, edited_mime))
                            status.set_text(
                                f"Previzualizare actualizată · {len(edited) // 1024} KB" if lang == "ro"
                                else f"Preview updated · {len(edited) // 1024} KB"
                            )

                        ui.button(t("Apply preview", lang), icon="tune", on_click=apply_preview).classes("pruvio-secondary w-full")

                        async def send_to_ocr():
                            if not state["original"]:
                                return
                            progress.visible = True
                            progress.set_value(0.35)
                            status.set_text(t("Reading receipt with Azure Document Intelligence…", lang))
                            payload = state.get("edited") or state["original"]
                            mime_type = state.get("edited_mime") or state["mime_type"]
                            filename = state["filename"] or "receipt.jpg"
                            if state.get("edited"):
                                filename = filename.rsplit(".", 1)[0] + "-edited.jpg"
                            try:
                                db = SessionLocal()
                                try:
                                    result = create_standalone_receipt_case(
                                        db=db,
                                        file_bytes=payload,
                                        original_filename=filename,
                                        mime_type=mime_type,
                                        user_id=user_id,
                                    )
                                    case_id = result["case"].id
                                finally:
                                    db.close()
                                progress.set_value(1.0)
                                status.set_text(t("Receipt ready.", lang))
                                ui.notify(t("Receipt processed successfully.", lang), type="positive", position="top")
                                ui.navigate.to(f"/receipt/{case_id}")
                            except Exception as error:
                                progress.set_value(0)
                                status.set_text(str(error))
                                ui.notify(str(error), type="negative", position="top")

                        ui.button(t("Send to OCR", lang), icon="document_scanner", on_click=send_to_ocr).classes("pruvio-primary w-full py-3")

                    async def on_upload(event):
                        try:
                            file_bytes, filename, mime_type = await _read_upload_event(event)
                            state["original"] = file_bytes
                            state["edited"] = None
                            state["filename"] = filename
                            state["mime_type"] = mime_type
                            state["rotation"] = 0
                            preview_panel.visible = True
                            progress.visible = False
                            if is_editable_image(mime_type, filename):
                                controls.visible = True
                                image_preview.visible = True
                                pdf_preview.visible = False
                                image_preview.set_source(data_uri(file_bytes, mime_type or "image/jpeg"))
                                status.set_text(
                                    "Imagine încărcată. Verifică imaginea completă, ajustează decuparea/scalarea și apoi trimite-o la OCR."
                                    if lang == "ro"
                                    else "Image loaded. Review the full image, adjust crop/scale, then send it to OCR."
                                )
                            else:
                                controls.visible = False
                                image_preview.visible = False
                                pdf_preview.visible = True
                                encoded = base64.b64encode(file_bytes).decode("ascii")
                                pdf_preview.set_content(
                                    f'<iframe src="data:application/pdf;base64,{encoded}" style="width:100%;height:70vh;border:1px solid #e2e8f0;border-radius:16px"></iframe>'
                                )
                                status.set_text(
                                    "PDF încărcat. Verifică documentul complet și apoi trimite-l la OCR. Editarea este disponibilă momentan pentru imagini."
                                    if lang == "ro"
                                    else "PDF loaded. Review the full document, then send it to OCR. Editing is currently available for images."
                                )
                        except Exception as error:
                            status.set_text(str(error))

                    ui.upload(
                        label=t("Take photo or choose receipt", lang),
                        on_upload=on_upload,
                        auto_upload=True,
                        max_file_size=10 * 1024 * 1024,
                    ).props(
                        'accept="image/jpeg,image/png,image/webp,application/pdf" color="dark" bordered flat'
                    ).classes("w-full mt-4")

                    ui.label(
                        "Fișierul este încărcat pentru previzualizare, dar nu este trimis către serviciul OCR până nu apeși Trimite la OCR."
                        if lang == "ro"
                        else "The file is loaded for preview, but it is not sent to the OCR service until you press Send to OCR."
                    ).classes("text-xs text-slate-400 mt-2")

        bottom_nav("upload", lang)
