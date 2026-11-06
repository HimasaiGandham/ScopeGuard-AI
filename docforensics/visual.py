"""Bounded blue-ink/printed-content overlap heuristic, not an authenticity test."""
from dataclasses import asdict
import io
import json
import subprocess
import sys
from PIL import Image, ImageOps, ImageChops, ImageFilter
from .models import Finding, FindingCategory, EvidenceRef, SourceRegion
from .trace import render_source_page

DPI = 144


def render(content, media_type, page):
    if media_type == 'application/pdf': return render_source_page(content,page,DPI)
    if page != 1: raise ValueError('An image has one page')
    with Image.open(io.BytesIO(content)) as image:
        if image.width*image.height > 25_000_000: raise ValueError('Image exceeds pixel limit')
        return ImageOps.exif_transpose(image).convert('RGB')


def detect(image):
    """Return normalized regions and measured signal counts at a fixed analysis width."""
    image=image.convert('RGB')
    if image.width*image.height > 25_000_000: raise ValueError('Image exceeds pixel limit')
    scale=min(1,1200/image.width,1700/image.height)
    image=image.resize((max(1,round(image.width*scale)),max(1,round(image.height*scale))),Image.Resampling.LANCZOS)
    red,green,blue=image.split()
    mask=ImageChops.multiply(ImageChops.subtract(blue,red).point(lambda p:255 if p>35 else 0),
                            ImageChops.subtract(blue,green).point(lambda p:255 if p>20 else 0))
    for channel,threshold,above in ((blue,90,True),(red,180,False),(green,180,False)):
        mask=ImageChops.multiply(mask,channel.point(lambda p:255 if (p>threshold if above else p<threshold) else 0))
    dark=ImageChops.lighter(ImageChops.lighter(red,green),blue).point(lambda p:255 if p<110 else 0)
    proximity=ImageChops.multiply(mask.filter(ImageFilter.MaxFilter(7)),dark)
    joined=bytearray(mask.filter(ImageFilter.MaxFilter(5)).tobytes());width,height=image.size
    observations=[]
    for start,value in enumerate(joined):
        if not value: continue
        joined[start]=0;stack=[start];left=right=start%width;top=bottom=start//width
        while stack:
            current=stack.pop();x,y=current%width,current//width
            left=min(left,x);right=max(right,x);top=min(top,y);bottom=max(bottom,y)
            for other in ((current-1 if x else -1),(current+1 if x+1<width else -1),current-width,current+width):
                if 0<=other<len(joined) and joined[other]: joined[other]=0;stack.append(other)
        box=(left,top,right+1,bottom+1)
        actual=mask.crop(box).getbbox()
        if actual is None:continue
        box=(left+actual[0],top+actual[1],left+actual[2],top+actual[3])
        w,h=box[2]-box[0],box[3]-box[1]
        count=mask.crop(box).histogram()[255]
        near=proximity.crop(box).histogram()[255]
        if max(w,h)<25 or min(w,h)<7 or count<40 or count/(w*h)<.015 or near<8:continue
        observations.append({'box':[box[0]/width,box[1]/height,box[2]/width,box[3]/height],
                             'blue_pixels':count,'near_dark_pixels':near,'analysis_size':[width,height]})
        if len(observations)>=50:break
    return observations


def inspect_case(store,case_id,timeout=30):
    record=store.get_case(case_id,verify_sources=False)
    documents=[];findings=[];scanned=0
    for document in record['documents']:
        entry={'document_id':document['document_id'],'filename':document['filename'],'pages':[]}
        local=[]
        try: _,content=store.read_original(case_id,document['document_id'])
        except (OSError,ValueError):
            entry.update(status='failed',error='Original missing or changed.');documents.append(entry);continue
        for page in range(1,document['page_count']+1):
            row={'page_number':page,'page_id':document['pages'][page-1]['page_id']}
            try:
                if scanned>=100:raise ValueError('Run page budget exceeded')
                scanned+=1
                process=subprocess.run([sys.executable,'-m','docforensics.visual','--worker',document['media_type'],str(page)],input=content,capture_output=True,timeout=timeout)
                if process.returncode:raise ValueError('Visual worker could not render or inspect page')
                signals=json.loads(process.stdout)
                row.update(status='completed',observations=len(signals),warning='Results may be truncated at 50 observations per page.' if len(signals)==50 else None)
                for signal in signals:
                    region=SourceRegion(page,*signal['box'])
                    finding=Finding(f"visual-{document['document_id']}-p{page}-{len(local)+1}",FindingCategory.VISUAL,
                        'Blue ink is close to or overlaps dark printed content.',
                        'A sufficiently large blue component contains dark pixels within its three-pixel analysis neighborhood. This may be an authorized correction, annotation, stamp, or scan artifact. It does not establish alteration or fraud. Confidence is uncalibrated; inspect the original.',
                        (EvidenceRef(document['document_id'],region,'Blue-ink/printed-content overlap review region'),),None)
                    local.append({'finding':asdict(finding),'signal':signal,'confidence_note':'Uncalibrated heuristic, not a probability.',
                                  'source_sha256':document['content_sha256'],'review_required':True})
            except subprocess.TimeoutExpired:row.update(status='failed',error='Visual page timeout; other pages continue.')
            except (OSError,ValueError,TypeError):row.update(status='failed',error='Visual page could not be inspected, or the 100-page run budget was reached.')
            entry['pages'].append(row)
        try:store.read_original(case_id,document['document_id'])
        except (OSError,ValueError):entry.update(status='failed',error='Source changed during inspection.');local=[]
        else:
            completed=sum(p['status']=='completed' for p in entry['pages'])
            entry['status']='completed' if completed==len(entry['pages']) else 'partial' if completed else 'failed'
        findings.extend(local);documents.append(entry)
    base=store.get_case(case_id,verify_sources=False)
    # Construct each shared finding during analysis; records preserve source hashes for later inspection.
    return {'case_id':case_id,'documents':documents,'findings':findings,'uploads':base['uploads'],
            'method':'blue_ink_near_dark_content_v1','limits':'English/text-independent color heuristic; no black-ink, font, signature, or invisible digital-edit detection. No findings does not establish authenticity.'}


if __name__=='__main__':
    try:sys.stdout.write(json.dumps(detect(render(sys.stdin.buffer.read(),sys.argv[2],int(sys.argv[3])))))
    except Exception:sys.exit(1)
