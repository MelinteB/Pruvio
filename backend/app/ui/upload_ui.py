import inspect

from nicegui import ui

from app.db.database import SessionLocal
from app.services.standalone_app_service import create_standalone_receipt_case
from app.ui.app_shell import app_header, bottom_nav, setup_page_head
from app.ui.auth_state import require_login


async def _read_upload_event(event) -> tuple[bytes, str, str | None]:
    """Support both older and newer NiceGUI upload event shapes."""
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
        setup_page_head("Upload receipt · Pruvio")

        user_id = require_login("/upload")
        if user_id is None:
            return

        with ui.element("main").classes("pruvio-page"):
            with ui.column().classes("pruvio-shell gap-4"):
                app_header("Scan receipt")

                with ui.card().classes("pruvio-card w-full p-6 sm:p-8"):
                    ui.label("Add a receipt").classes(
                        "text-2xl sm:text-3xl font-black text-slate-950"
                    )
                    ui.label(
                        "Take a photo or upload JPG, PNG, WEBP or PDF. Pruvio will extract quantities, unit prices, totals and currency."
                    ).classes("text-sm text-slate-500 max-w-2xl")

                    progress = ui.linear_progress(value=0).classes("w-full mt-3")
                    progress.visible = False
                    status = ui.label("").classes("text-sm text-slate-500")

                    async def on_upload(event):
                        progress.visible = True
                        progress.set_value(0.25)
                        status.set_text("Uploading receipt…")

                        try:
                            file_bytes, filename, mime_type = await _read_upload_event(event)
                            progress.set_value(0.45)
                            status.set_text("Reading receipt with Azure Document Intelligence…")

                            db = SessionLocal()
                            try:
                                result = create_standalone_receipt_case(
                                    db=db,
                                    file_bytes=file_bytes,
                                    original_filename=filename,
                                    mime_type=mime_type,
                                    user_id=user_id,
                                )
                                case_id = result["case"].id
                            finally:
                                db.close()

                            progress.set_value(1.0)
                            status.set_text("Receipt ready.")
                            ui.notify("Receipt processed successfully.", type="positive", position="top")
                            ui.navigate.to(f"/receipt/{case_id}")

                        except Exception as error:
                            progress.set_value(0)
                            status.set_text(str(error))
                            ui.notify(f"Could not process receipt: {error}", type="negative", position="top")

                    with ui.column().classes("w-full items-stretch gap-3 mt-3"):
                        ui.upload(
                            label="Take photo or choose receipt",
                            on_upload=on_upload,
                            auto_upload=True,
                            max_file_size=10 * 1024 * 1024,
                        ).props(
                            'accept="image/jpeg,image/png,image/webp,application/pdf" '
                            'color="dark" bordered flat'
                        ).classes("w-full")

                        ui.label(
                            "Tip: use a sharp photo with the whole receipt visible. Translation is added only for non-Romanian, non-English receipts."
                        ).classes("text-xs text-slate-400")

        bottom_nav("upload")
