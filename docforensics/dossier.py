"""Export the selected reviewer records as a source-linked PDF snapshot."""

from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4
from xml.sax.saxutils import escape, quoteattr

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate

from .context_api import case_with_fields
from .ingestion import SourceChangedError
from .models import SourceRegion
from .reviewer import RUN, record_fingerprint


MAX_REPORT_ENTRIES = 2000
MAX_REPORT_TEXT = 1_000_000
FONT_DIRECTORY = Path(reportlab.__file__).parent / 'fonts'
for name, file in (('DossierBody', 'Vera.ttf'), ('DossierBold', 'VeraBd.ttf')):
    pdfmetrics.registerFont(TTFont(name, str(FONT_DIRECTORY / file)))
pdfmetrics.registerFontFamily('DossierBody', normal='DossierBody', bold='DossierBold')
GLYPHS = pdfmetrics.getFont('DossierBody').face.charToGlyph
INK = colors.HexColor('#192D42')
BLUE = colors.HexColor('#1E5482')


def display_text(value):
    """Expose unsupported glyphs losslessly as Unicode escapes."""
    return ''.join(
        char if char in '\n\t' or ord(char) in GLYPHS else f'\\u{{{ord(char):04X}}}'
        for char in str(value)
    )


def markup(value):
    return escape(display_text(value)).replace('\n', '<br/>').replace('\t', '    ')


def confidence(value):
    return 'Unavailable' if value is None else str(value)


class PDFReport:
    def __init__(self):
        self.flow = []
        self.text_size = 0
        self.styles = {
            'body': ParagraphStyle('Body', fontName='DossierBody', fontSize=9.5, leading=14,
                                   textColor=INK, spaceAfter=6),
            'title': ParagraphStyle('Title', fontName='DossierBold', fontSize=25, leading=30,
                                    textColor=INK, spaceAfter=10, keepWithNext=True),
            'section': ParagraphStyle('Section', fontName='DossierBold', fontSize=15, leading=20,
                                      textColor=BLUE, spaceBefore=13, spaceAfter=6, keepWithNext=True),
            'label': ParagraphStyle('Label', fontName='DossierBold', fontSize=10, leading=15,
                                    textColor=INK, spaceBefore=5, spaceAfter=3, keepWithNext=True),
        }

    def add(self, text, style='body', url=None):
        self.text_size += len(text)
        if self.text_size > MAX_REPORT_TEXT:
            raise ValueError('Selected results exceed the PDF text limit. Split the packet and rerun the checks.')
        content = markup(text)
        if url:
            content = f'<link href={quoteattr(url)} color="#1E5482">{content}</link>'
        self.flow.append(Paragraph(content, self.styles[style]))

    @contextmanager
    def together(self):
        start = len(self.flow)
        yield
        self.flow[start:] = [KeepTogether(self.flow[start:])]

    def finish(self, case_id):
        buffer = BytesIO()
        document = SimpleDocTemplate(buffer, pagesize=A4, topMargin=47, bottomMargin=47,
                                     rightMargin=48, leftMargin=48,
                                     title='ScopeGuard AI Investigation Dossier', author='ScopeGuard AI')

        def footer(canvas, doc):
            canvas.setStrokeColor(colors.HexColor('#D4E0EA'))
            canvas.line(48, 37, A4[0] - 48, 37)
            canvas.setFont('DossierBody', 8)
            canvas.setFillColor(INK)
            canvas.drawString(48, 23, case_id)
            canvas.drawRightString(A4[0] - 48, 23, f'Page {doc.page}')

        document.build(self.flow, onFirstPage=footer, onLaterPages=footer)
        return buffer.getvalue()


class EvidenceIndex:
    def __init__(self, documents):
        self.documents = {doc['document_id']: doc for doc in documents}
        self.entries = {}

    def reference(self, source):
        document_id = source['document_id']
        region = SourceRegion(**source['region'])
        document = self.documents[document_id]
        if region.page_number > document['page_count']:
            raise ValueError('Saved evidence page exceeds the original page count')
        key = document_id, region
        if key not in self.entries:
            self.entries[key] = f'E{len(self.entries) + 1:03d}'
        return f'{self.entries[key]} ({document["filename"]}, page {region.page_number})'

    def write(self, pdf, endpoint):
        if not self.entries:
            pdf.add('The selected runs contain no extracted fields or findings with source regions.')
        for (document_id, region), label in self.entries.items():
            doc = self.documents[document_id]
            page = region.page_number
            with pdf.together():
                pdf.add(f'{label} | {doc["filename"]} | page {page}', 'label')
                pdf.add(f'Document {document_id} | Page ID {doc["pages"][page - 1]["page_id"]}')
                pdf.add(f'Normalized region (left, top, right, bottom): {region.x1}, {region.y1}, {region.x2}, {region.y2}')
                pdf.add('Open verified original page in the local workspace',
                        url=f'{endpoint}/documents/{document_id}/pages/{page}')


def write_overview(pdf, case, reports):
    pdf.add('1 Document overview', 'section')
    pdf.add(f'{len(case["documents"])} saved document(s). Storage status: {case["status"]}.')
    for upload in case['uploads']:
        detail = upload.get('error', {}).get('message') or upload.get('message')
        if upload.get('duplicate_of'):
            detail = f'{detail or ""} Same as {upload["duplicate_of"]}.'.strip()
        pdf.add(f'Upload {upload["input_index"]} | {upload["filename"]} | {upload["status"]}'
                + (f' | {detail}' if detail else ''))

    by_stage = {}
    for stage in ('extraction', 'visual'):
        documents = reports[stage]['documents']
        indexed = {doc['document_id']: doc for doc in documents}
        if len(indexed) != len(documents) or indexed.keys() != {doc['document_id'] for doc in case['documents']}:
            raise ValueError(f'Saved {stage} inventory does not match the case')
        by_stage[stage] = indexed

    incomplete = 0
    for document in case['documents']:
        document_id = document['document_id']
        with pdf.together():
            pdf.add(f'{document["filename"]} | {document["page_count"]} page(s)', 'label')
            pdf.add(f'{document_id} | {document["media_type"]} | {document["size_bytes"]} bytes')
            pdf.add(f'Source SHA-256: {document["content_sha256"]}')
        for stage, inventory in by_stage.items():
            result = inventory[document_id]
            status = result['status']
            pages = result['pages']
            if result['filename'] != document['filename'] or status not in ('completed', 'partial', 'failed'):
                raise ValueError(f'Saved {stage} result does not match the original')
            if pages or status != 'failed':
                identities = [(p['page_number'], p['page_id']) for p in pages]
                if identities != [(p['page_number'], p['page_id']) for p in document['pages']]:
                    raise ValueError(f'Saved {stage} pages do not match the original')
            incomplete += status != 'completed'
            pdf.add(f'{stage.capitalize()} status: {status}')
            if result.get('error'):
                pdf.add(result['error'])
            for page in pages:
                details = [page['status']]
                details += [page[key] for key in ('method', 'document_type', 'layout', 'error', 'warning', 'layout_warning')
                            if page.get(key)]
                pdf.add(f'{stage.capitalize()} page {page["page_number"]} | ' + ' | '.join(details))
    return incomplete


def write_findings(pdf, index, items, decisions, kind, endpoint, run):
    if not items:
        pdf.add('The selected run recorded zero leads.')
    for item in items:
        finding = item['finding']
        finding_id = finding['finding_id']
        event = decisions[kind, finding_id]
        decision = event['decision']
        pdf.add(f'{finding_id} | {finding["observation"]}', 'label')
        pdf.add(finding['explanation'])
        pdf.add(f'Category: {finding["category"]} | Confidence: {confidence(finding["confidence"])}')
        if item.get('confidence_note'):
            pdf.add(item['confidence_note'])
        for observed in item.get('observations', []):
            pdf.add(f'Observed {observed["name"]}: {observed["value"]} | {index.reference(observed["source"])}')
            pdf.add(f'Normalized comparison value: {observed["comparison"]["normalized"]}')
        for source in finding['evidence']:
            reference = index.reference(source)
            excerpt = f' | {source["excerpt"]}' if source.get('excerpt') else ''
            pdf.add(f'Evidence {reference}{excerpt}')
        if kind == 'visual':
            pdf.add('Open verified visual crop in the local workspace',
                    url=f'{endpoint}/visual/{run}/evidence/{finding_id}/crop')
        pdf.add(f'Review status: {decision["state"]} | Reviewer: {decision["reviewer"]}')
        pdf.add(f'Decision {event["event_id"]} | {event["occurred_at"]}')
        pdf.add(f'Reviewer note: {decision["note"]}')


def render_dossier(case, reports, decisions, runs, dossier_id, created_at, reviewer, endpoint):
    extraction, context, visual = (reports[kind] for kind in ('extraction', 'context', 'visual'))
    fields = extraction['fields']
    count = len(fields) + len(decisions) + len(case['uploads']) + len(context['warnings'])
    for stage in (extraction, visual):
        count += sum(len(doc['pages']) + 1 for doc in stage['documents'])
    for report in (context, visual):
        count += sum(len(item['finding']['evidence']) for item in report['findings'])
    if count > MAX_REPORT_ENTRIES:
        raise ValueError('Selected results exceed the PDF entry limit. Split the packet and rerun the checks.')

    pdf = PDFReport()
    index = EvidenceIndex(case['documents'])
    pdf.add('Investigation Dossier', 'title')
    pdf.add(f'ScopeGuard AI | Case {case["case_id"]} | Dossier {dossier_id}')
    pdf.add(f'Generated {created_at} | Requested by {reviewer}')
    pdf.add('Snapshot of selected local checks and human decisions. Findings indicate items for review. Authenticity remains unverified.')
    for kind, run in runs.items():
        pdf.add(f'{kind.capitalize()} run {run} | Record SHA-256: {record_fingerprint(reports[kind])}')

    incomplete = write_overview(pdf, case, reports)
    pdf.add('2 Extracted information', 'section')
    pdf.add(f'{len(fields)} structured field(s). {extraction["limits"]}')
    if not fields:
        pdf.add('The selected extraction run returned no structured fields.')
    for field in fields:
        pdf.add(f'{field["name"]}: {field["value"]}', 'label')
        pdf.add(f'{field["field_id"]} | Confidence: {confidence(field["confidence"])} | {index.reference(field["source"])}')

    pdf.add('3 Contextual analysis', 'section')
    grouping = 'confirmed' if context['same_entity_confirmed'] else 'unconfirmed (cross-document checks skipped)'
    pdf.add(f'Related-document grouping: {grouping}. {context["rules"]}')
    for warning in context['warnings']:
        location = warning.get('document_id', '')
        if warning.get('source'):
            location = index.reference(warning['source'])
        pdf.add(f'Coverage warning: {warning["message"]}' + (f' | {location}' if location else ''))
    write_findings(pdf, index, context['findings'], decisions, 'context', endpoint, runs['context'])

    pdf.add('4 Visual forensic findings', 'section')
    pdf.add(f'Method: {visual["method"]}. {visual["limits"]}')
    write_findings(pdf, index, visual['findings'], decisions, 'visual', endpoint, runs['visual'])

    pdf.add('5 Evidence and traceability', 'section')
    pdf.add('Evidence IDs link the fields and findings above to original filenames, document IDs, pages, and normalized coordinates. Coordinates start at the upper-left of the displayed page.')
    pdf.add('Evidence links require the local workspace at the export address. Use the document and page IDs to locate evidence after moving the PDF. Unsupported display characters appear as Unicode escapes.')
    index.write(pdf, endpoint)

    pdf.add('6 Investigation summary', 'section')
    states = Counter(event['decision']['state'] for event in decisions.values())
    pdf.add(f'{len(context["findings"])} contextual lead(s), {len(visual["findings"])} visual lead(s). '
            f'{states["accepted_for_review"]} accepted for further review and {states["dismissed"]} dismissed.')
    pdf.add(f'{incomplete} document-stage result(s) were incomplete or failed. See Document overview for page status and errors.')
    pdf.add('Follow-up: compare extracted values with their original regions, investigate retained leads, '
            'and retry or manually inspect failed, unreadable, or unsupported pages.')
    pdf.add('Coverage is limited to supported text layouts, contextual comparisons, and visual signals. '
            'Unknown confidence remains unavailable. A zero-lead result leaves authenticity unverified.')
    return pdf.finish(case['case_id'])


def dossier_directory(reviews, case_id):
    return reviews.folder(case_id) / 'dossiers'


def saved_dossiers(reviews, case_id):
    folder = dossier_directory(reviews, case_id)
    if folder.resolve() != folder:
        raise OSError('Invalid dossier storage')
    records = [(file.stem, file.stat().st_mtime) for file in folder.glob('*.pdf')
               if RUN.fullmatch(file.stem) and file.is_file() and not file.is_symlink()]
    return [{'dossier_id': identifier, 'created_at': datetime.fromtimestamp(stamp, timezone.utc).isoformat()}
            for identifier, stamp in sorted(records, key=lambda record: record[1], reverse=True)[:50]]


def dossier_path(reviews, case_id, dossier_id):
    if not RUN.fullmatch(dossier_id):
        raise FileNotFoundError('Dossier not found')
    folder = dossier_directory(reviews, case_id)
    path = folder / f'{dossier_id}.pdf'
    if folder.resolve() != folder or path.is_symlink() or not path.is_file():
        raise FileNotFoundError('Dossier not found')
    return path


def create_dossier(reviews, case_id, runs, reviewer, acknowledge, base_url):
    case, reports, decisions = reviews.dossier_selection(case_id, runs, reviewer, acknowledge)
    case_with_fields(reviews.store._as_case(case), reports['extraction'])
    dossier_id = uuid4().hex
    created_at = datetime.now(timezone.utc).isoformat()
    endpoint = f'{base_url}/api/ingestion/cases/{case_id}'
    content = render_dossier(case, reports, decisions, runs, dossier_id, created_at, reviewer, endpoint)
    if reviews.store.get_case(case_id) != case:
        raise SourceChangedError('Case changed during PDF generation')
    folder = dossier_directory(reviews, case_id)
    folder.mkdir(exist_ok=True)
    if folder.resolve() != folder:
        raise OSError('Invalid dossier storage')
    # Publish only a complete file, with exclusive creation even if a UUID collides.
    temporary = None
    try:
        with NamedTemporaryFile(dir=folder, suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.link(temporary, folder / f'{dossier_id}.pdf')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {'dossier_id': dossier_id, 'created_at': created_at,
            'download_url': f'/api/ingestion/cases/{case_id}/dossiers/{dossier_id}'}
