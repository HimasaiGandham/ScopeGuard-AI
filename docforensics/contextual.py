"""Conservative comparisons of observed fields; no evaluation-label input."""
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from itertools import combinations
import re
import unicodedata

from .models import Finding, FindingCategory, SourceRegion, EvidenceRef, InvestigationCase

EXPECTED = {
    'student_registration': ('student_name', 'student_id', 'course_code'),
    'enrollment_confirmation': ('student_name', 'student_id', 'course_code'),
    'coursework_submission': ('student_name', 'student_id', 'submission_date', 'course_code'),
}
CROSS_KEYS = frozenset(('student_name', 'student_id', 'course_code', 'date_of_birth'))


def normalize(name: str, value: str) -> dict:
    text = ' '.join(unicodedata.normalize('NFKC', value).split())
    result = {'original': value, 'normalized': text.casefold(), 'comparable': bool(text), 'reason': None}
    if not text:
        result.update(comparable=False, reason='Empty observed value requires review.')
    elif name.endswith('_date') or name == 'date_of_birth':
        result.update(normalized=None, comparable=False, reason='Unsupported or ambiguous date format; no date order assumed.')
        for date_format in ('%Y-%m-%d', '%d %B %Y', '%d %b %Y'):
            try:
                result.update(normalized=datetime.strptime(text, date_format).date().isoformat(), comparable=True, reason=None)
                break
            except ValueError:
                pass
    elif name in ('amount', 'total', 'fixed_costs', 'variable_costs', 'optional_costs'):
        match = re.fullmatch(r'(?:(USD|INR|EUR)\s+|([$₹€])\s*)?([+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?)', text, re.I)
        if match:
            currency = (match[1] or {'$':'USD', '₹':'INR', '€':'EUR'}.get(match[2], '')).upper()
            amount = Decimal(match[3].replace(',', ''))
            exact = format(amount, 'f')
            if '.' in exact: exact = exact.rstrip('0').rstrip('.')
            if amount == 0: exact = '0'
            result['normalized'] = currency + ':' + exact
        else:
            result.update(comparable=False, normalized=None, reason='Unsupported numeric format or units; no amount inferred.')
    elif name in ('student_id', 'course_code'):
        result['normalized'] = text.upper()  # Punctuation and meaningful internal spaces are preserved.
    return result


def analyze(case: InvestigationCase, *, same_entity: bool = False) -> dict:
    if len(case.fields) > 500:
        raise ValueError('Comparison supports up to 500 extracted fields; split the packet.')
    if type(same_entity) is not bool:
        raise ValueError('same_entity must be explicitly true or false')
    fields = {f.field_id: normalize(f.name, f.value) for f in case.fields}
    findings, details, warnings = [], [], []
    for field in case.fields:
        if not fields[field.field_id]['comparable']:
            warnings.append({'field_id':field.field_id, 'message':fields[field.field_id]['reason'], 'source':asdict(field.source)})
    def emit(kind, category, related, message, evidence=None):
        if len(findings) >= 200:
            if not any(w.get('limit') for w in warnings):
                warnings.append({'limit':True,'message':'Finding limit reached (200); results are partial. Split the packet.'})
            return
        sources = tuple(f.source for f in related) if evidence is None else evidence
        unscored = any(f.confidence is None or f.confidence < .7 for f in related)
        explanation = message + ' Check the cited originals. Differences may reflect extraction errors or legitimate revisions; this is not a manipulation finding.'
        if unscored: explanation += ' One or more values have unknown or low extraction confidence.'
        finding = Finding(f'context-{len(findings)+1:04d}', category, kind.replace('_',' ').capitalize(), explanation, sources, None)
        findings.append(finding)
        details.append({'finding':asdict(finding), 'kind':kind, 'field_ids':[f.field_id for f in related],
                        'observations':[{'field_id':f.field_id, 'name':f.name, 'value':f.value,
                                         'comparison':fields[f.field_id], 'source':asdict(f.source)} for f in related],
                        'review_required':True})
    for doc in case.documents:
        observed = [f for f in case.fields if f.source.document_id == doc.document_id]
        for name in sorted({f.name for f in observed}):
            selected = [f for f in observed if f.name == name]
            for left, right in combinations(selected, 2):
                a,b = fields[left.field_id], fields[right.field_id]
                if not a['comparable'] or not b['comparable']: continue
                equal = a['normalized'] == b['normalized']
                emit('repeated_field' if equal else 'internal_conflict', FindingCategory.WITHIN_DOCUMENT, (left,right),
                     f'{name} appears more than once in {doc.filename}: {left.value!r} on page {left.source.region.page_number} and {right.value!r} on page {right.source.region.page_number}. '
                     + ('Equivalent repeated values may be intentional.' if equal else 'The supported normalization rules leave different values.'))
        if doc.document_type in EXPECTED:
            for name in EXPECTED[doc.document_type]:
                if not any(f.name == name and f.value.strip() for f in observed):
                    emit('missing_extracted_field',FindingCategory.WITHIN_DOCUMENT,(),
                         f'Expected {name} was not extracted from the supported {doc.document_type} layout in {doc.filename}. This may be an OCR omission; document absence is not established.',
                         (EvidenceRef(doc.document_id,SourceRegion(1,0,0,1,1),'Whole-page review anchor for an expected but unextracted field'),))
    if same_entity:
        for name in sorted(CROSS_KEYS):
            selected = [f for f in case.fields if f.name == name]
            for left,right in combinations(selected,2):
                if left.source.document_id == right.source.document_id: continue
                a,b=fields[left.field_id],fields[right.field_id]
                if a['comparable'] and b['comparable'] and a['normalized'] != b['normalized']:
                    emit('cross_document_conflict',FindingCategory.CROSS_DOCUMENT,(left,right),
                         f'The reviewer grouped these documents as the same student and enrollment. {name} differs: {left.value!r} in {left.source.document_id}, page {left.source.region.page_number}, versus {right.value!r} in {right.source.document_id}, page {right.source.region.page_number}.')
    else:
        warnings.append({'message':'Cross-document comparison skipped: confirm that the documents concern the same student.'})
    # Enforce all shared source-link and page validation rules on the resulting findings.
    InvestigationCase(case.case_id,case.documents,case.fields,tuple(findings),case.audit_events)
    return {'case_id':case.case_id,'same_entity_confirmed':same_entity,'fields':[
        {'field':asdict(f),'comparison':fields[f.field_id]} for f in case.fields],
        'findings':details,'warnings':warnings,'rules':'Conservative deterministic comparisons; leads for human review, not authenticity decisions.'}
