"""Printable expense report with the saved original documents as annexes."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from app.models.case import Case
from app.models.document import Document
from app.services.document_service import resolve_document_path

FONTS = Path(__file__).with_name('fonts')
pdfmetrics.registerFont(TTFont('Pruvs', str(FONTS / 'DejaVuSans.ttf')))
pdfmetrics.registerFont(TTFont('PruvsBold', str(FONTS / 'DejaVuSans-Bold.ttf')))
pdfmetrics.registerFontFamily('Pruvs', normal='Pruvs', bold='PruvsBold')
NAVY = colors.HexColor('#14264c')
BLUE = colors.HexColor('#0756df')


def safe(value):
    return escape(str(value if value is not None else ''))


def page_number(c, doc):
    c.setFont('Pruvs', 8)
    c.setFillColor(colors.HexColor('#6d7790'))
    c.drawString(17*mm, 11*mm, 'PRUVS  |  EXPENSE REPORT')
    c.drawRightString(A4[0]-17*mm, 11*mm, str(doc.page))


def summary_pdf(report_id, snapshot, created_at, annexes):
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=17*mm, rightMargin=17*mm,
                            topMargin=18*mm, bottomMargin=19*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='PruvsTitle', fontName='PruvsBold', fontSize=17, leading=23,
                              textColor=NAVY, spaceAfter=11))
    styles.add(ParagraphStyle(name='PruvsSection', fontName='PruvsBold', fontSize=10, leading=15,
                              textColor=BLUE, spaceBefore=12, spaceAfter=6))
    styles.add(ParagraphStyle(name='PruvsBody', fontName='Pruvs', fontSize=8, leading=12, spaceAfter=4))
    styles.add(ParagraphStyle(name='PruvsSmall', fontName='Pruvs', fontSize=7, leading=10))
    styles.add(ParagraphStyle(name='PruvsHead', fontName='PruvsBold', fontSize=7, leading=10,
                              textColor=colors.white))
    p = lambda value, kind='PruvsBody': Paragraph(safe(value), styles[kind])
    story = [p(snapshot['title'], 'PruvsTitle'),
             p(f"Report #{report_id}  |  Prepared {created_at:%Y-%m-%d}  |  {snapshot.get('trip_profile') or 'Expense report'}")]
    company, details = snapshot['company'], snapshot['details']
    story += [p('Company and assignment', 'PruvsSection'),
              p(f"{company.get('name','')}  |  Tax ID: {company.get('tax_id','')}  |  VAT: {company.get('vat_number','')}"),
              p(f"{company.get('address','')}  {company.get('country','')}  |  Registration: {company.get('registration_number','')}"),
              p(f"Employee: {snapshot.get('employee','')}  |  Department: {company.get('department','')}"),
              p(f"Purpose: {details.get('purpose','')}"),
              p(f"Route: {details.get('origin','')} to {details.get('destination','')}  |  "
                f"{details.get('departure_date','')} to {details.get('return_date','')}"),
              p(f"Project: {details.get('project','')}  |  Cost center: {details.get('cost_center','')}  |  "
                f"Approver: {details.get('approver','')}")]
    for key, value in details.items():
        if value and key not in {'purpose','origin','destination','departure_date','return_date',
                                 'project','cost_center','approver','advance_currency','advance_amount'}:
            story.append(p(f"{key.replace('_',' ').capitalize()}: {value}"))
    story.append(p('Itemized expenses', 'PruvsSection'))
    widths = [10*mm, 23*mm, 58*mm, 36*mm, 24*mm, 24*mm]
    grid = [[p(v, 'PruvsHead') for v in ('#', 'Date', 'Supplier / source', 'Category', 'Claim', 'VAT')]]
    for index, item in enumerate(snapshot['items'], 1):
        desc = item.get('merchant') or item.get('filename') or 'Receipt'
        reason = item.get('business_reason') or item.get('notes') or ''
        reference = item.get('invoice_number') or item.get('filename') or ''
        source_details = ' | '.join(x for x in (reference, reason) if x)
        grid.append([p(index,'PruvsSmall'), p(item.get('expense_date',''),'PruvsSmall'),
                     p(desc + (' | '+source_details if source_details else ''),'PruvsSmall'),
                     p(item.get('category','').replace('_',' ') + ' | ' + item.get('paid_by',''),'PruvsSmall'),
                     p(f"{item.get('claimed_amount','')} {item.get('currency','')}" +
                       (f" | {item['converted_amount']} {snapshot['reference_conversion']['currency']}" if item.get('fx_rate') and snapshot.get('reference_conversion') else ''),'PruvsSmall'),
                     p(f"{item.get('vat_amount','')} {item.get('currency','')}",'PruvsSmall')])
    table = Table(grid, colWidths=widths, repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),
                               ('VALIGN',(0,0),(-1,-1),'TOP'),
                               ('BOTTOMPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),6),
                               ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f4f7fc')]),
                               ('LINEBELOW',(0,0),(-1,-1),.25,colors.HexColor('#dce4ee'))]))
    story += [table, p('Totals by currency', 'PruvsSection')]
    for currency,total in snapshot['totals'].items():
        story.append(p(f"{currency}: expense {total}  |  employee paid "
                       f"{snapshot['employee_paid'].get(currency,'0.00')}  |  reimbursement "
                       f"{snapshot['reimbursement'].get(currency,'0.00')}"))
    reference = snapshot.get('reference_conversion')
    if reference:
        story += [p('Indicative reference conversion', 'PruvsSection'),
                  p(f"Total: {reference['total']} {reference['currency']}  |  {(reference.get('provider') or 'ECB').upper()} published {reference.get('date') or 'manual / same currency'}"),
                  p('Original claim amounts remain authoritative. Rates are indicative, saved when the report was created; check company reimbursement policy.'),
                  p(reference.get('source_url') or ('Manual rate entered by report creator' if reference.get('manual') else 'Same currency'))]
        for item in snapshot['items']:
            if item.get('fx_rate'):
                story.append(p(f"{item['expense_date']}: 1 {item['currency']} = {item['fx_rate']} {reference['currency']}  |  " + ('Manual rate' if item.get('fx_manual') else f"{(item.get('fx_provider') or 'ECB').upper()} {item.get('fx_date') or 'same currency'}")))
    if details.get('advance_amount') not in (None,'','0','0.00'):
        story.append(p(f"Company advance: {details['advance_amount']} {details.get('advance_currency','')}"))
    story += [Spacer(1,8*mm), p('Prepared by ____________________    Approved by ____________________    Date __________'),
              p('Annex: source documents', 'PruvsSection')]
    for index, (_, status, _) in enumerate(annexes, 1):
        story.append(p(f"{index}. {snapshot['items'][index-1].get('filename') or snapshot['items'][index-1].get('merchant') or 'Receipt'}: {status}"))
    story.append(Spacer(1,4*mm))
    story.append(p('Amounts for split bills are limited to your settled share. Check company policy, VAT treatment and originals before submission.'))
    doc.build(story, onFirstPage=page_number, onLaterPages=page_number)
    output.seek(0)
    return output


def cover_pdf(item, number, status):
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=A4)
    c.setFont('PruvsBold', 15)
    c.setFillColor(NAVY)
    c.drawString(17*mm, A4[1]-27*mm, f'ANNEX {number} - SOURCE DOCUMENT')
    c.setFont('Pruvs', 10)
    text = c.beginText(17*mm, A4[1]-43*mm)
    for line in (f"Date: {item.get('expense_date','')}",
                 f"Claimed amount: {item.get('claimed_amount','')} {item.get('currency','')}",
                 f"Source: {item.get('kind','')}",
                 f"Document: {(item.get('filename') or item.get('merchant') or '')[:90]}",
                 f"Availability: {status}"):
        text.textLine(line)
    c.drawText(text)
    c.showPage();c.save();output.seek(0)
    return output


def image_pdf(path):
    """Keep a tall receipt legible by placing consecutive strips on separate A4 pages."""
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=A4)
    with Image.open(path) as opened:
        if opened.width * opened.height > 40_000_000:
            raise ValueError('Image dimensions exceed the safe PDF limit.')
        image = ImageOps.exif_transpose(opened).convert('RGB')
        width,height=image.size
        strip = max(1,int(width*1.42))
        for top in range(0,height,strip):
            part=image.crop((0,top,width,min(height,top+strip)))
            available_w,available_h=A4[0]-34*mm,A4[1]-34*mm
            scale=min(available_w/part.width,available_h/part.height)
            w,h=part.width*scale,part.height*scale
            c.drawImage(ImageReader(part),(A4[0]-w)/2,(A4[1]-h)/2,width=w,height=h)
            c.showPage()
    c.save();output.seek(0)
    return output


def render_expense_pdf(db, uid, report_id, snapshot, created_at):
    """Use the immutable report snapshot; never attach another user's private scan."""
    annexes=[]
    budget=100*1024*1024
    for item in snapshot['items']:
        case=db.get(Case,item['case_id'])
        if case is None or case.user_id!=uid:
            annexes.append((None,'Source scan belongs to another account; personal share is documented above.',None))
            continue
        doc=(db.query(Document).filter_by(id=item['document_id'],case_id=case.id).first()
             if item.get('document_id') else
             db.query(Document).filter_by(case_id=case.id).order_by(Document.id.desc()).first())
        path=resolve_document_path(doc)
        if path is None:
            annexes.append((None,'Original file unavailable; restore it from the receipt page.',None))
            continue
        if path.stat().st_size>budget:
            raise ValueError('Scanned documents exceed the 100 MB PDF export limit. Make smaller reports.')
        budget-=path.stat().st_size
        annexes.append((path,'Original scan attached',path.suffix.lower()))
    writer=PdfWriter()
    writer.append(PdfReader(summary_pdf(report_id,snapshot,created_at,annexes)))
    for number,(item,(path,status,extension)) in enumerate(zip(snapshot['items'],annexes),1):
        writer.append(PdfReader(cover_pdf(item,number,status)))
        if path is None:continue
        try:
            document=PdfReader(str(path),strict=False) if extension=='.pdf' else PdfReader(image_pdf(path))
            if document.is_encrypted or len(document.pages)>100:
                raise ValueError('Encrypted or oversized PDF source.')
            writer.append(document)
        except (ValueError,OSError,UnidentifiedImageError,Image.DecompressionBombError,PdfReadError) as exc:
            # A damaged source should not silently produce a partial PDF.
            raise ValueError(f"Cannot attach scan #{number}. Restore or replace its source document.") from exc
    output=BytesIO();writer.write(output);output.seek(0)
    return output
