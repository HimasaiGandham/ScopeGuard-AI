// Run against an isolated local upload_app; requires Playwright and a browser.
// NODE_PATH supplies Playwright when installed outside this checkout.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');

(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE?{executablePath:process.env.BROWSER_EXECUTABLE}:{})});
 try{
  const page=await browser.newPage(),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const base=process.env.BASE_URL||'http://127.0.0.1:8769';
  await page.goto(base+'/ingest');
  async function fixture(mark){return Buffer.from(await page.evaluate(mark=>{
   const canvas=document.createElement('canvas');canvas.width=600;canvas.height=400;
   const c=canvas.getContext('2d');c.fillStyle='white';c.fillRect(0,0,600,400);
   c.fillStyle='black';c.font='30px Arial';c.fillText('NF-2048',80,125);
   if(mark){c.strokeStyle='rgb(35,65,160)';c.lineWidth=3;c.beginPath();c.moveTo(80,110);c.lineTo(220,118);c.lineTo(82,125);c.lineTo(218,132);c.stroke();}
   return canvas.toDataURL('image/png').split(',')[1];
  },mark),'base64');}
  const clean={name:'clean.png',mimeType:'image/png',buffer:await fixture(false)};
  const marked={name:'marked.png',mimeType:'image/png',buffer:await fixture(true)};
  async function upload(files){
   await page.goto(base+'/ingest');await page.locator('#case-files').setInputFiles(files);
   await page.locator('#create-case').click();
   await page.waitForFunction(()=>!document.getElementById('create-case').disabled&& !document.getElementById('case-panel').hidden);
  }
  let checks=0;page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/visual'))checks++;});
  assert.equal(await page.locator('#create-case').isDisabled(),true);
  const picker=page.waitForEvent('filechooser');
  await page.getByRole('button',{name:'Choose files'}).press('Enter');
  await (await picker).setFiles([marked]);
  assert.equal(await page.locator('#selection-count').innerText(),'1 file selected');
  assert.equal(await page.locator('#selected-files li').innerText(),'marked.png');
  await page.locator('#create-case').click();
  await page.waitForFunction(()=>!document.getElementById('choose-files').disabled&&!document.getElementById('case-panel').hidden);
  assert.match(await page.locator('#check-status').innerText(),/Possible alteration/);
  assert.match(await page.locator('#case-rows').innerText(),/contents unverified/);
  const crop=page.locator('#check-results a').first();
  assert.equal((await page.request.get(base+await crop.getAttribute('href'))).status(),200);
  const afterUpload=checks;await page.reload();
  await page.waitForFunction(()=>!document.getElementById('choose-files').disabled);
  assert.equal(checks,afterUpload,'refresh must reuse saved visual run');
  assert.match(await page.locator('#check-status').innerText(),/Possible alteration/);
  await page.locator('#retry-check').click();await page.waitForFunction(()=>!document.getElementById('retry-check').disabled);
  assert.equal(checks,afterUpload+1,'retry creates one new visual run');
  await page.goto(base+'/ingest');
  const dataTransfer=await page.evaluateHandle(file=>{
   const transfer=new DataTransfer();
   transfer.items.add(new File([Uint8Array.from(file.bytes)],file.name,{type:file.mimeType}));
   return transfer;
  },{name:clean.name,mimeType:clean.mimeType,bytes:Array.from(clean.buffer)});
  await page.locator('#drop-zone').dispatchEvent('dragover',{dataTransfer});
  assert.equal(await page.locator('#drop-zone.dragging').count(),1);
  await page.locator('#drop-zone').dispatchEvent('drop',{dataTransfer});
  await dataTransfer.dispose();
  assert.equal(await page.locator('#drop-zone.dragging').count(),0);
  assert.equal(await page.locator('#selected-files li').innerText(),'clean.png');
  await page.locator('#create-case').click();
  await page.waitForFunction(()=>!document.getElementById('choose-files').disabled&&!document.getElementById('case-panel').hidden);
  assert.match(await page.locator('#check-status').innerText(),/does not mean.*correct or genuine/);
  assert.match(await page.locator('#check-results').innerText(),/authenticity unverified/);
  await upload([marked,{...marked,name:'copy.png'},clean,{name:'broken.pdf',mimeType:'application/pdf',buffer:Buffer.from('broken')}]);
  assert.match(await page.locator('#counts').innerText(),/1 identical file duplicate.*1 rejected/);
  assert.match(await page.locator('#check-results').innerText(),/marked.png: Possible alteration/);
  assert.match(await page.locator('#check-results').innerText(),/clean.png: No supported visual marks/);
  await page.route('**/review-run/visual/*',async route=>{
   const response=await route.fetch(),view=await response.json();view.report.documents[0].status='partial';
   view.report.documents[0].pages[0].error='Visual page timeout; other pages continue.';
   await route.fulfill({response,json:view});
  });
  await page.reload();await page.waitForFunction(()=>!document.getElementById('choose-files').disabled);
  assert.match(await page.locator('#check-status').innerText(),/checks are incomplete/);
  assert.match(await page.locator('#check-results').innerText(),/Visual page timeout/);
  await page.unroute('**/review-run/visual/*');
  await page.route('**/visual',route=>route.request().method()==='POST'?route.fulfill({status:500,json:{detail:'Visual check unavailable'}}):route.continue());
  await upload([marked]);
  assert.match(await page.locator('#check-status').innerText(),/Check failed — authenticity unverified/);
  assert.match(await page.locator('#status').innerText(),/alteration check failed/);
  assert.equal(await page.locator('#check-results a').count(),0,'no stale evidence after failure');
  await page.unroute('**/visual');
  await page.locator('#retry-check').click();await page.waitForFunction(()=>!document.getElementById('retry-check').disabled);
  assert.match(await page.locator('#check-status').innerText(),/Possible alteration/);
  await upload([{name:'broken.pdf',mimeType:'application/pdf',buffer:Buffer.from('broken')}]);
  assert.equal(await page.locator('#visual-summary').isVisible(),false);
  await page.locator('#case-files').setInputFiles([clean]);await page.locator('#create-case').click();
  await page.waitForFunction(()=>!document.getElementById('create-case').disabled);
  assert.equal(await page.locator('#visual-summary').isVisible(),true);
  assert.match(await page.locator('#check-status').innerText(),/No supported visual marks/);
  await page.setViewportSize({width:360,height:800});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),360,'results must fit a narrow viewport');
  assert.deepEqual(errors,[]);
  console.log('PASS: keyboard file picker, drag-and-drop, narrow layout, automatic marks, saved-run reuse, retry, mixed results, failure recovery, and zero browser errors.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
