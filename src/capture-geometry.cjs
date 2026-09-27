'use strict';

// L3-L5 only. L1/L2 quality and temporal stability remain upstream gates.
const fs = require('node:fs');
const path = require('node:path');
const defaults = JSON.parse(fs.readFileSync(path.join(__dirname, '../configs/capture-templates.json'), 'utf8'));
const center = b => [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2];
const width = b => b[2] - b[0];
const height = b => b[3] - b[1];
const area = b => width(b) * height(b);
function fractionInside(b, parent) {
  return Math.max(0, Math.min(b[2], parent[2]) - Math.max(b[0], parent[0])) *
    Math.max(0, Math.min(b[3], parent[3]) - Math.max(b[1], parent[1])) / area(b);
}
function features(b, reference) {
  const [cx, cy] = center(b);
  return [(cx-reference[0])/width(reference), (cy-reference[1])/height(reference),
    width(b)/width(reference), height(b)/height(reference)];
}
function displacement(a, b, reference) {
  const ca = center(a), cb = center(b);
  return [(ca[0]-cb[0])/width(reference), (ca[1]-cb[1])/height(reference)];
}
function validate(input, config) {
  if (!input || !config.vehicle_types.includes(input.vehicle_type)) throw new Error('INVALID_VEHICLE_TYPE');
  if (!config.shot_types.includes(input.shot_type)) throw new Error('INVALID_SHOT_TYPE');
  if (input.shot_type.startsWith('interior_') && !['left','right'].includes(input.entry_side)) throw new Error('ENTRY_SIDE_REQUIRED');
  if (input.coordinate_space !== config.coordinate_space) throw new Error('INVALID_COORDINATE_SPACE');
  if (input.image_mirrored !== false) throw new Error('UNMIRROR_IMAGE_FIRST');
  if (input.source !== 'camera_raw') throw new Error('RAW_CAMERA_IMAGE_REQUIRED');
  if (!Array.isArray(input.detections) || input.detections.length > 200) throw new Error('INVALID_DETECTIONS');
  for (const d of input.detections) {
    if (!Number.isInteger(d.class_id) || !Object.hasOwn(config.model_classes, d.class_id)) throw new Error('INVALID_CLASS_ID');
    if (!Number.isFinite(d.confidence) || d.confidence < 0 || d.confidence > 1) throw new Error('INVALID_CONFIDENCE');
    if (!Array.isArray(d.box) || d.box.length !== 4 || d.box.some(v => !Number.isFinite(v) || v < 0 || v > 1) || width(d.box) <= 0 || height(d.box) <= 0) throw new Error('INVALID_BOX');
  }
}
function scoreTemplate(template, detections, reference, thresholds) {
  // Each detected object may satisfy at most one anchor of the same class.
  // Optional objects do not reduce a missing-required-feature penalty.
  const required = template.anchors.filter(a => a.required);
  if (required.length < template.min_valid_features) return {id:template.id,shot_type:template.shot_type,valid:false,error:null,reason:'INSUFFICIENT_TEMPLATE_FEATURES'};
  const classes = [...new Set(required.map(a => a.class_id))];
  const matches = {};
  for (const classId of classes) {
    const anchors = required.filter(a => a.class_id === classId);
    const candidates = detections.filter(d => d.class_id === classId)
      .sort((a,b) => b.confidence-a.confidence).slice(0,8);
    if (candidates.length < anchors.length) return {id:template.id,shot_type:template.shot_type,valid:false,error:null,reason:'MISSING_REQUIRED_FEATURE',missing_class_id:classId};
    let best = null;
    function visit(i, used, chosen, sum) {
      if (i === anchors.length) {if (!best || sum < best.sum) best = {sum,chosen:[...chosen]};return;}
      const a = anchors[i], target = features(a.box, template.reference_box);
      for (let j=0;j<candidates.length;j++) {
        if (used.has(j)) continue;
        const f = features(candidates[j].box, reference);
        const residual = f.map((v,k) => (v-target[k])/a.tolerance[k]);
        const error = Math.sqrt(residual.reduce((s,v)=>s+v*v,0)/4);
        used.add(j);chosen.push({anchor:a,detection:candidates[j],error,residual});
        visit(i+1,used,chosen,sum+error*error);chosen.pop();used.delete(j);
      }
    }
    visit(0,new Set(),[],0);
    for (const match of best.chosen) matches[match.anchor.id] = match;
  }
  const errors = Object.values(matches).map(m=>m.error);
  const relationships = [];
  for (const [a,b] of template.relationships) {
    const observed = displacement(matches[a].detection.box,matches[b].detection.box,reference);
    const expected = displacement(matches[a].anchor.box,matches[b].anchor.box,template.reference_box);
    const tolerance = [0,1].map(k => Math.hypot(matches[a].anchor.tolerance[k],matches[b].anchor.tolerance[k]));
    const error = Math.sqrt(observed.reduce((sum,v,k)=>sum+((v-expected[k])/tolerance[k])**2,0)/2);
    errors.push(error);relationships.push({anchors:[a,b],observed,expected,error});
  }
  const error = Math.sqrt(errors.reduce((s,e)=>s+e*e,0)/errors.length);
  return {id:template.id,shot_type:template.shot_type,valid:true,error,
    within_tolerance:error<=thresholds.max_match_error && Math.max(...errors)<=thresholds.max_per_anchor_error,
    relationships,anchors:Object.values(matches).map(m=>({id:m.anchor.id,error:m.error,residual:m.residual,box:m.detection.box}))};
}
function analyzeGeometry(input, config=defaults) {
  validate(input,config);
  const detections = input.detections.filter(d => d.confidence>=config.thresholds.detection_confidence);
  const templates = config.templates.filter(t => (t.vehicle_type===input.vehicle_type || t.vehicle_type==='shared') &&
    (input.shot_type.startsWith('exterior_') ? t.shot_type.startsWith('exterior_') : t.shot_type===input.shot_type && t.entry_side===input.entry_side));
  const target = templates.find(t=>t.shot_type===input.shot_type);
  if (!target) throw new Error('TEMPLATE_NOT_FOUND');
  const base = {rules_version:config.version,calibration_status:config.calibration_status,vehicle_type:input.vehicle_type,
    requested_slot:input.shot_type,entry_side:input.entry_side??null,classification_is_advisory:true,geometry_passed:false,can_capture:false,
    ignored_raw_model_class_ids:config.ignored_raw_model_class_ids,checks:{L3:'not_evaluated',L4:'not_evaluated',L5:'not_evaluated'}};
  const stop = (code, level, status='fail', detail={}) => ({...base,status,code,failed_level:level,...detail});
  if (target.evaluation_mode==='guide_only') {
    base.checks={L3:'not_applicable',L4:'not_applicable',L5:'unknown'};
    return stop('FRONT_SEAT_EVIDENCE_UNAVAILABLE','L5','unknown',{
      requested_template_matches:null,suggested_slot:null,
      guidance:'請依側門示意圖拍入前排椅背與坐墊；目前模型無法自動確認前排覆蓋。'
    });
  }
  let reference = [0,0,1,1], objects=detections;
  if (target.reference_class_id !== null) {
    const cars=detections.filter(d=>d.class_id===target.reference_class_id);
    if (!cars.length) return stop('SUBJECT_NOT_DETECTED',null,'unknown');
    if (cars.length>1) return stop('MULTIPLE_SUBJECTS',null,'unknown');
    reference=cars[0].box;
    objects=detections.filter(d=>fractionInside(d.box,reference)>=config.thresholds.association_fraction);
    const edge=target.edge_margin;
    if (reference[0]<edge || reference[1]<edge || reference[2]>1-edge || reference[3]>1-edge) {
      base.checks.L3='fail';return stop('SUBJECT_NEAR_EDGE','L3');
    }
    const w=width(reference), h=height(reference);
    if (w<target.body_width_range[0] || h<target.body_height_range[0]) {base.checks.L3='fail';return stop('SUBJECT_TOO_SMALL','L3');}
    if (w>target.body_width_range[1] || h>target.body_height_range[1]) {base.checks.L3='fail';return stop('SUBJECT_TOO_LARGE','L3');}
    base.checks.L3='pass';
    const c=center(reference), expected=center(target.reference_box);
    const delta=c.map((v,i)=>v-expected[i]);
    if (delta.some((v,i)=>Math.abs(v)>target.body_center_tolerance[i])) {base.checks.L4='fail';return stop('OFF_CENTER','L4','fail',{offset:delta});}
    base.checks.L4='pass';
  } else {base.checks.L3='not_applicable';base.checks.L4='not_applicable';}
  const scores=templates.map(t=>scoreTemplate(t,objects,reference,config.thresholds));
  const requested=scores.find(s=>s.shot_type===input.shot_type);
  const ranked=scores.filter(s=>s.valid).sort((a,b)=>a.error-b.error);
  const best=ranked[0], second=ranked[1];
  const gap=best && second ? second.error-best.error : null;
  const distinct=!!best && (!second || gap>=config.thresholds.min_runner_up_gap);
  const classified=best?.within_tolerance && distinct ? best.shot_type : null;
  const detail={requested_template_matches:requested.valid && requested.within_tolerance,
    suggested_slot:classified,match_gap:gap,scores,template_error_is_probability:false};
  if (!requested.valid) {base.checks.L5='unknown';return stop(requested.reason,'L5','unknown',detail);}
  if (classified && classified!==input.shot_type) {base.checks.L5='fail';return stop('POSSIBLE_WRONG_SLOT','L5','fail',detail);}
  if (!requested.within_tolerance) {base.checks.L5='fail';return stop('GEOMETRY_MISMATCH','L5','fail',detail);}
  if (!distinct) {base.checks.L5='unknown';return stop('AMBIGUOUS_TEMPLATES','L5','unknown',detail);}
  if (config.calibration_status!=='calibrated') {base.checks.L5='unknown';return stop('TEMPLATE_NOT_CALIBRATED','L5','unknown',detail);}
  base.checks.L5='pass';
  // Full capture PASS must also require L1/L2 and frame stability, not this module alone.
  return {...base,status:'geometry_pass',code:'GEOMETRY_MATCH',failed_level:null,geometry_passed:true,...detail};
}
module.exports={analyzeGeometry,scoreTemplate,displacement,defaults};
