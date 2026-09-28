'use strict';

const test=require('node:test');
const assert=require('node:assert/strict');
const {PNG}=require('pngjs');
const {decodeImage,orientPixels}=require('../src/image-decode.cjs');
const {analyzeQuality}=require('../src/photo-quality.cjs');
const {analyzeCapture,StabilityTracker}=require('../src/capture-decision.cjs');
const {createServer}=require('../src/capture-api.cjs');

function png(kind='checker'){
  const p=new PNG({width:256,height:256});
  for(let y=0;y<256;y++)for(let x=0;x<256;x++){
    const i=(y*256+x)*4;
    const v=kind==='black'?0:kind==='white'?255:((Math.floor(x/4)+Math.floor(y/4))%2?25:230);
    p.data[i]=p.data[i+1]=p.data[i+2]=v;p.data[i+3]=255;
  }
  return PNG.sync.write(p);
}
function metadata(extra={}){return {schema_version:'1.0',case_id:'CASE-1',capture_session_id:'SESSION-1',
  capture_phase:'checkout',vehicle_type:'sedan',shot_type:'exterior_front_left',frame_id:1,
  mode:'preview',image_mirrored:false,source:'camera_raw',...extra};}
function detector(detections=[]){return {ready:true,modelVersion:'test-model',start(){},close(){},
  async analyze(){return {detections,width:256,height:256};}};}
function goodDetections(){
  const config=require('../configs/capture-templates.json');
  const t=config.templates.find(t=>t.id==='sedan_exterior_front_left');
  return [{class_id:0,confidence:.99,box:t.reference_box},
    ...t.anchors.filter(a=>a.required).map(a=>({class_id:a.class_id,confidence:.99,box:a.box}))];
}

test('image limits and formats reject before inference',()=>{
  assert.equal(decodeImage(png()).width,256);
  assert.throws(()=>decodeImage(Buffer.from('not image')),{code:'UNSUPPORTED_IMAGE_FORMAT'});
  assert.throws(()=>decodeImage(png(),{maxPixels:100}),{code:'IMAGE_DIMENSIONS_EXCEEDED'});
});
test('EXIF rotation maps pixels to the corrected image coordinates',()=>{
  const data=Buffer.from([1,0,0,255,2,0,0,255,3,0,0,255,4,0,0,255,5,0,0,255,6,0,0,255]);
  const rotated=orientPixels(data,2,3,6);
  assert.deepEqual([rotated.width,rotated.height],[3,2]);
  assert.deepEqual([0,4,8].map(i=>rotated.data[i]),[5,3,1]);
});
test('L1 has priority over L2 and stops model',async()=>{
  let called=false;const d=detector();d.analyze=async()=>{called=true;throw Error('should not infer')};
  const b=png('black');const result=await analyzeCapture({metadata:metadata(),imageBuffer:b,
    decoded:decodeImage(b),detector:d});
  assert.equal(result.guidance.code,'TOO_DARK');assert.equal(result.capture_quality.checks.L2,'unknown');
  assert.equal(result.capture_quality.checks.L3,'not_evaluated');assert.equal(called,false);
});
test('a valid sharp frame runs model and uncalibrated template cannot grant PASS',async()=>{
  const b=png();const result=await analyzeCapture({metadata:metadata(),imageBuffer:b,
    decoded:decodeImage(b),detector:detector(goodDetections())});
  assert.equal(analyzeQuality(decodeImage(b)).checks.L2,'pass');
  assert.equal(result.guidance.code,'TEMPLATE_NOT_CALIBRATED');
  assert.equal(result.guidance.can_capture,false);
  assert.equal(result.capture_quality.checks.L1,'pass');
  assert.equal(result.capture_quality.checks.L5,'unknown');
});
test('aligned calibrated preview enables shutter on the first passing frame',async()=>{
  const b=png();
  const base=require('../configs/capture-templates.json');
  const config={...base,calibration_status:'calibrated',
    templates:base.templates.filter(t=>t.id==='sedan_exterior_front_left')};
  const result=await analyzeCapture({metadata:metadata(),imageBuffer:b,decoded:decodeImage(b),
    detector:detector(goodDetections()),config});
  assert.equal(result.status,'ready');
  assert.equal(result.guidance.can_capture,true);
  assert.equal(result.guidance.review_required,false);
  assert.equal(result.capture_quality.passed,true);
});
test('after sustained alignment trouble, shutter opens with a mandatory human review flag',async()=>{
  const b=png(),tracker=new StabilityTracker({manualAfterMs:20000});
  let tick=0;
  const args={imageBuffer:b,decoded:decodeImage(b),detector:detector(goodDetections()),tracker,
    now:()=>tick};
  const first=await analyzeCapture({...args,metadata:metadata()});
  assert.equal(first.guidance.can_capture,false);
  assert.equal(first.guidance.manual_review_remaining_ms,20000);
  tick=20000;
  const second=await analyzeCapture({...args,metadata:metadata({frame_id:2})});
  assert.equal(second.status,'manual_capture_available');
  assert.equal(second.guidance.code,'MANUAL_REVIEW_AVAILABLE');
  assert.equal(second.guidance.can_capture,true);
  assert.equal(second.guidance.review_required,true);
  assert.equal(second.capture_quality.passed,false);
  assert.equal(second.capture_quality.primary_issue,'TEMPLATE_NOT_CALIBRATED');
  assert.equal(second.recommended_action,'human_review');
  const final=await analyzeCapture({...args,metadata:metadata({frame_id:3,mode:'final'})});
  assert.equal(final.status,'needs_review');
  assert.equal(final.guidance.review_required,true);
});
test('a timed-out session cannot bypass dark-image or missing-subject gates',async()=>{
  const tracker=new StabilityTracker({manualAfterMs:20000});
  let tick=0;
  const b=png('black');
  const args={imageBuffer:b,decoded:decodeImage(b),detector:detector(goodDetections()),tracker,
    now:()=>tick};
  await analyzeCapture({...args,metadata:metadata()});
  tick=20000;
  const dark=await analyzeCapture({...args,metadata:metadata({frame_id:2})});
  assert.equal(dark.guidance.can_capture,false);
  assert.equal(dark.guidance.code,'TOO_DARK');
  const sharp=png();
  const missing=await analyzeCapture({...args,imageBuffer:sharp,decoded:decodeImage(sharp),
    detector:detector(),metadata:metadata({frame_id:3})});
  assert.equal(missing.guidance.can_capture,false);
  assert.equal(missing.guidance.code,'SUBJECT_NOT_DETECTED');
});
test('the manual-review timer resets after a long preview interruption',async()=>{
  const b=png(),tracker=new StabilityTracker({manualAfterMs:20000,sessionIdleMs:60000});
  let tick=0;
  const args={imageBuffer:b,decoded:decodeImage(b),detector:detector(goodDetections()),tracker,
    now:()=>tick};
  await analyzeCapture({...args,metadata:metadata()});
  tick=61000;
  const resumed=await analyzeCapture({...args,metadata:metadata({frame_id:2})});
  assert.equal(resumed.guidance.can_capture,false);
  assert.equal(resumed.guidance.manual_review_remaining_ms,20000);
});
test('final photo must pass its own quality checks even after manual shutter unlocks',async()=>{
  const b=png(),tracker=new StabilityTracker({manualAfterMs:20000});
  let tick=0;
  const args={imageBuffer:b,decoded:decodeImage(b),detector:detector(goodDetections()),tracker,
    now:()=>tick};
  await analyzeCapture({...args,metadata:metadata()});
  tick=20000;
  const unlocked=await analyzeCapture({...args,metadata:metadata({frame_id:2})});
  assert.equal(unlocked.guidance.can_capture,true);
  const dark=png('black');
  const final=await analyzeCapture({...args,imageBuffer:dark,decoded:decodeImage(dark),
    metadata:metadata({frame_id:3,mode:'final'})});
  assert.equal(final.guidance.can_capture,false);
  assert.equal(final.guidance.code,'TOO_DARK');
});
test('bright background with dark subject returns backlight advice',async()=>{
  const p=new PNG({width:256,height:256});
  for(let y=0;y<256;y++)for(let x=0;x<256;x++){
    const i=(y*256+x)*4,inside=x>=26&&x<230&&y>=69&&y<218;
    const v=inside?((x+y)%8<4?20:42):((x+y)%8<4?223:240);
    p.data[i]=p.data[i+1]=p.data[i+2]=v;p.data[i+3]=255;
  }
  const b=PNG.sync.write(p);const result=await analyzeCapture({metadata:metadata(),imageBuffer:b,
    decoded:decodeImage(b),detector:detector(goodDetections())});
  assert.equal(result.guidance.code,'BACKLIT');
  assert.equal(result.capture_quality.checks.L1,'fail');
  assert.equal(result.capture_quality.checks.L3,'not_evaluated');
});
test('right-side front cabin is guide-only with this model',async()=>{
  const b=png();const result=await analyzeCapture({metadata:metadata({shot_type:'interior_front',entry_side:'right'}),
    imageBuffer:b,decoded:decodeImage(b),detector:detector()});
  assert.equal(result.guidance.code,'FRONT_SEAT_EVIDENCE_UNAVAILABLE');
});
test('stale preview frame is rejected',async()=>{
  const b=png('black'),tracker=new StabilityTracker();
  const args={metadata:metadata(),imageBuffer:b,decoded:decodeImage(b),detector:detector(),tracker};
  await analyzeCapture(args);
  await assert.rejects(()=>analyzeCapture(args),/STALE_FRAME/);
});
test('multipart API validates image and metadata, returns structured advice',async(t)=>{
  const server=createServer({detector:detector()});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  t.after(()=>new Promise(resolve=>server.close(resolve)));
  const base=`http://127.0.0.1:${server.address().port}`;
  let r=await fetch(base+'/ready');assert.equal(r.status,200);
  assert.deepEqual((await r.json()).service_classes,
    {'0':'car','1':'headlight','2':'license_plate','3':'rear_seat_bench','4':'steering_wheel','5':'wheel'});
  const form=new FormData();form.append('metadata',JSON.stringify(metadata()));
  form.append('image',new Blob([png('black')],{type:'image/png'}),'frame.png');
  r=await fetch(base+'/api/v1/capture/analyze',{method:'POST',body:form});
  assert.equal(r.status,200);let data=await r.json();
  assert.equal(data.guidance.code,'TOO_DARK');assert.equal(data.capture_quality.failed_level,'L1');
  const bad=new FormData();bad.append('metadata',JSON.stringify(metadata({vehicle_type:'truck'})));
  bad.append('image',new Blob([png()],{type:'image/png'}),'frame.png');
  r=await fetch(base+'/api/v1/capture/analyze',{method:'POST',body:bad});
  assert.equal(r.status,422);data=await r.json();assert.equal(data.code,'INVALID_VEHICLE_TYPE');
});
