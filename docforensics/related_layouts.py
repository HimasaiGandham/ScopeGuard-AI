"""Explicit small registration/confirmation templates for the related-document demo."""
from dataclasses import asdict
from .models import ExtractedField, EvidenceRef, SourceRegion

LABELS={'student name':'student_name','student id':'student_id','course code':'course_code','date of birth':'date_of_birth'}


def recognize_related(lines, document_id, page_number):
    headings={line['text'].casefold().strip() for line in lines}
    kind = ('student_registration' if 'student registration' in headings else
            'enrollment_confirmation' if 'enrollment confirmation' in headings else None)
    if kind is None: return None
    fields=[]
    for line in lines:
        for label,name in LABELS.items():
            if not line['text'].casefold().strip().startswith(label): continue
            words=[w for w in line['words'][len(label.split()):] if w['text'].strip(':')]
            if not words: continue
            value=' '.join(w['text'] for w in words)
            region=SourceRegion(page_number,min(w['box'][0] for w in words),min(w['box'][1] for w in words),max(w['box'][2] for w in words),max(w['box'][3] for w in words))
            fields.append(asdict(ExtractedField(f'{document_id}-p{page_number}-related-{len(fields)+1}',name,value,EvidenceRef(document_id,region,value),None)))
    if len({f['name'] for f in fields}) < 2: return None
    return {'layout':kind,'document_type':kind,'text':'\n'.join(l['text'] for l in lines),
            'fields':fields,'sections':[], 'tables':[], 'layout_warning':'Controlled demo template; all extracted values require source review.'}
