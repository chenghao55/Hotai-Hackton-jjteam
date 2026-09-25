'use strict';
const assert=require('node:assert/strict');
const {analyzeGeometry,scoreTemplate,displacement,defaults}=require('../src/capture-geometry.cjs');
const clone=x=>JSON.parse(JSON.stringify(x));
function fixture(shot='exterior_front_left',type='sedan',entry='left') {
 const t=defaults.templates.find(t=>t.shot_type===shot&&(t.vehicle_type===type||t.vehicle_type==='shared')&&(!t.entry_side||t.entry_side===entry));
 return {vehicle_type:type,shot_type:shot,...(shot.startsWith('interior_')?{entry_side:entry}:{}),source:'camera_raw',image_mirrored:false,coordinate_space:defaults.coordinate_space,
 detections:[...(t.reference_class_id===null?[]:[{class_id:0,confidence:.98,box:[...t.reference_box]}]),
 ...t.anchors.filter(a=>a.required).map(a=>({class_id:a.class_id,confidence:.95,box:[...a.box]}))]};
}
function runTests(){const results=[];const test=(name,fn)=>{fn();results.push(name);};
 test('front-end slot is mandatory',()=>{const p=fixture();delete p.shot_type;assert.throws(()=>analyzeGeometry(p),/INVALID_SHOT_TYPE/)});
 test('vehicle family is mandatory',()=>{const p=fixture();p.vehicle_type='unknown';assert.throws(()=>analyzeGeometry(p),/INVALID_VEHICLE_TYPE/)});
 test('reject image with UI overlays',()=>{const p=fixture();p.source='screenshot';assert.throws(()=>analyzeGeometry(p),/RAW_CAMERA/)});
 test('reject mirrored coordinate space',()=>{const p=fixture();p.image_mirrored=true;assert.throws(()=>analyzeGeometry(p),/UNMIRROR/)});
 test('reject non-finite boxes',()=>{const p=fixture();p.detections[0].box[0]=NaN;assert.throws(()=>analyzeGeometry(p),/INVALID_BOX/)});
 test('reject inverted boxes',()=>{const p=fixture();p.detections[0].box=[.8,.2,.1,.8];assert.throws(()=>analyzeGeometry(p),/INVALID_BOX/)});
 test('reject unknown model class IDs',()=>{const p=fixture();p.detections[0].class_id=7;assert.throws(()=>analyzeGeometry(p),/INVALID_CLASS/)});
 test('excluded class 1 cannot alter output or shift class IDs',()=>{const p=fixture();const before=analyzeGeometry(p);p.detections.push({class_id:1,confidence:1,box:[0,0,1,1]});assert.deepEqual(analyzeGeometry(p),before)});
 test('absence of subject is unknown',()=>{const p=fixture();p.detections=p.detections.filter(d=>d.class_id!==0);assert.equal(analyzeGeometry(p).code,'SUBJECT_NOT_DETECTED')});
 test('multiple cars are not merged',()=>{const p=fixture();p.detections.push({class_id:0,confidence:.9,box:[.01,.01,.2,.2]});assert.equal(analyzeGeometry(p).code,'MULTIPLE_SUBJECTS')});
 test('low confidence feature is missing, not passed',()=>{const p=fixture();p.detections.find(d=>d.class_id===3).confidence=.01;assert.equal(analyzeGeometry(p).code,'MISSING_REQUIRED_FEATURE')});
 test('one wheel cannot fill two anchors',()=>{const p=fixture();p.detections.splice(p.detections.findIndex(d=>d.class_id===6),1);assert.equal(analyzeGeometry(p).code,'MISSING_REQUIRED_FEATURE')});
 test('neighbor plate cannot satisfy target vehicle',()=>{const p=fixture();p.detections.find(d=>d.class_id===3).box=[.01,.01,.08,.08];assert.equal(analyzeGeometry(p).code,'MISSING_REQUIRED_FEATURE')});
 test('edge risk has priority over geometry',()=>{const p=fixture();p.detections[0].box[0]=.01;const r=analyzeGeometry(p);assert.equal(r.code,'SUBJECT_NEAR_EDGE');assert.equal(r.checks.L5,'not_evaluated')});
 test('small car fails L3',()=>{const p=fixture();p.detections[0].box=[.35,.35,.65,.65];assert.equal(analyzeGeometry(p).code,'SUBJECT_TOO_SMALL')});
 test('vertical framing offset fails L4, not camera height',()=>{const p=fixture();p.detections[0].box=[.1,.07,.9,.65];assert.equal(analyzeGeometry(p).code,'OFF_CENTER')});
 test('missing all parts never matches a template',()=>{const p=fixture();p.detections=p.detections.slice(0,1);assert.equal(analyzeGeometry(p).code,'MISSING_REQUIRED_FEATURE')});
 test('horizontal sign survives equal Euclidean distances',()=>{const a=[.4,.4,.6,.6],b=[.7,.4,.9,.6],c=[.1,.4,.3,.6];const r=[0,0,1,1];assert(displacement(b,a,r)[0]>0);assert(displacement(c,a,r)[0]<0)});
 test('object ordering does not change assignment',()=>{const p=fixture();const r=analyzeGeometry(p);p.detections.reverse();assert.deepEqual(analyzeGeometry(p),r)});
 test('size and translation do not alter body-relative geometry',()=>{const p=fixture();const t=defaults.templates[0];const ref=p.detections[0].box;const score=scoreTemplate(t,p.detections,ref,defaults.thresholds);const moved=p.detections.map(d=>({...d,box:d.box.map((v,i)=>v*.8+(i%2?.06:.1))}));const score2=scoreTemplate(t,moved,moved[0].box,defaults.thresholds);assert(Math.abs(score.error-score2.error)<1e-10)});
 test('ambiguous equally close templates are refused',()=>{const p=fixture();const c=clone(defaults);const other=clone(c.templates[0]);other.id='ambiguous';other.shot_type='exterior_rear_right';c.templates=c.templates.filter(t=>t.shot_type!=='exterior_rear_right');c.templates.push(other);assert.equal(analyzeGeometry(p,c).code,'AMBIGUOUS_TEMPLATES')});
 test('draft templates never allow capture',()=>{for(const t of defaults.templates){const p=fixture(t.shot_type,t.vehicle_type==='shared'?'sedan':t.vehicle_type,t.entry_side);const r=analyzeGeometry(p);assert.equal(r.geometry_passed,false);assert.equal(r.can_capture,false)}});
 test('synthetic calibrated geometry still cannot alone allow capture',()=>{const p=fixture();const c=clone(defaults);c.templates=[c.templates[0]];c.calibration_status='calibrated';const r=analyzeGeometry(p,c);assert.equal(r.geometry_passed,true);assert.equal(r.can_capture,false)});
 test('wrong requested slot is never overwritten',()=>{const p=fixture('exterior_front_right');p.shot_type='exterior_front_left';const r=analyzeGeometry(p);assert.equal(r.requested_slot,'exterior_front_left');assert.equal(r.geometry_passed,false)});
 test('rear templates do not require headlight',()=>{for(const t of defaults.templates.filter(t=>t.shot_type.includes('rear_')))assert(!t.anchors.some(a=>a.class_id===2&&a.required))});
 test('interior rear does not require steering wheel',()=>{const p=fixture('interior_rear');const r=analyzeGeometry(p);assert.equal(r.requested_template_matches,true)});
 test('interior entry side is required',()=>{const p=fixture('interior_rear');delete p.entry_side;assert.throws(()=>analyzeGeometry(p),/ENTRY_SIDE_REQUIRED/)});
 test('right front door does not require a visible steering wheel',()=>{const p=fixture('interior_front','sedan','right');p.detections=[];const r=analyzeGeometry(p);assert.equal(r.code,'FRONT_SEAT_EVIDENCE_UNAVAILABLE');assert.equal(r.entry_side,'right')});
 test('left and right rear doors use different templates',()=>{for(const side of ['left','right']){const r=analyzeGeometry(fixture('interior_rear','sedan',side));assert.equal(r.requested_template_matches,true);assert.equal(r.scores.length,1);assert(r.scores[0].id.includes(side+'_door'))}});
 return {passed:results.length,tests:results,scope:'Synthetic geometry and contract tests only; no model inference or real-image accuracy claim.'};
}
if(require.main===module)console.log(JSON.stringify(runTests(),null,2));
module.exports={runTests,fixture};
