'use strict';

const {randomUUID,createHash}=require('node:crypto');
const {analyzeQuality}=require('./photo-quality.cjs');
const {analyzeGeometry,defaults:rules}=require('./capture-geometry.cjs');

const messages={
  TOO_DARK:'光線不足，請開啟補光或移到較明亮的位置。',
  OVEREXPOSED:'畫面過亮，請避開直射光並調整曝光。',
  BACKLIT:'車身比背景暗，請微調站位或曝光，讓車身細節清楚。',
  BLUR:'畫面模糊，請拿穩手機並重新對焦。',
  LOW_DETAIL:'目前無法確認清晰度，請將車輛或座椅清楚放入畫面。',
  SUBJECT_NOT_DETECTED:'未找到目標車輛，請將整台車放入取景框。',
  MULTIPLE_SUBJECTS:'畫面有多台車，請只拍攝目標車輛。',
  SUBJECT_NEAR_EDGE:'車身接近畫面邊緣，請保留車頭、車尾與輪胎。',
  SUBJECT_TOO_SMALL:'車身太小，請稍微靠近。',
  SUBJECT_TOO_LARGE:'車身太大，請稍微後退並保留完整車身。',
  OFF_CENTER:'請微調手機方向，讓車身對齊取景框。',
  MISSING_REQUIRED_FEATURE:'關鍵部位未清楚入鏡，請依示意圖調整拍攝位置。',
  POSSIBLE_WRONG_SLOT:'畫面較像另一個拍攝角度，請確認目前指定的車角。',
  GEOMETRY_MISMATCH:'請依拍攝示意圖調整構圖，讓必要部位入鏡。',
  AMBIGUOUS_TEMPLATES:'目前無法明確分辨拍攝角度，請依示意圖調整。',
  TEMPLATE_NOT_CALIBRATED:'構圖基準尚待校正，請依示意圖調整；稍後可拍照交人工確認。',
  FRONT_SEAT_EVIDENCE_UNAVAILABLE:'請從側門拍入前排椅背與坐墊；目前無法自動確認前排完整。',
  MANUAL_REVIEW_AVAILABLE:'已嘗試對齊一段時間；可以先拍照，照片須交由人工審理。',
  STABILIZING:'請保持鏡頭穩定，準備拍照。',
  READY:'構圖、特徵與畫質符合要求，請拍照。'
};

class StabilityTracker {
  constructor({holdMs=0,manualAfterMs=rules.manual_review_after_ms,sessionIdleMs=60000,maxEntries=2000}={}){
    this.holdMs=holdMs;this.manualAfterMs=manualAfterMs;this.sessionIdleMs=sessionIdleMs;
    this.maxEntries=maxEntries;this.items=new Map();
  }
  key(m){return [m.case_id,m.capture_session_id,m.capture_phase,m.shot_type,m.entry_side||''].join('|');}
  begin(m,now=Date.now()){
    const key=this.key(m),old=this.items.get(key);
    if(m.mode!=='preview')return {key,stale:false};
    if(old&&m.frame_id<=old.frame_id)return {key,stale:true};
    const active=old&&now-old.last_seen<=this.sessionIdleMs;
    this.items.set(key,{frame_id:m.frame_id,started_at:active?old.started_at:now,
      first_good:active?old.first_good:null,last_seen:now});
    if(this.items.size>this.maxEntries){const first=this.items.keys().next().value;this.items.delete(first);}
    return {key,stale:false,previous:old};
  }
  finish(m,token,good,now=Date.now()){
    if(m.mode!=='preview')return good;
    const current=this.items.get(token.key);
    if(!current||current.frame_id!==m.frame_id)return false;
    current.first_good=good?(current.first_good??now):null;
    current.last_seen=now;
    return good&&now-current.first_good>=this.holdMs;
  }
  manualTiming(token,now=Date.now()){
    const current=this.items.get(token.key);
    if(!current||now-current.last_seen>this.sessionIdleMs)return {available:false,remaining_ms:this.manualAfterMs};
    const elapsed=Math.max(0,now-current.started_at);
    return {available:elapsed>=this.manualAfterMs,
      remaining_ms:Math.max(0,this.manualAfterMs-elapsed)};
  }
}

function validateMetadata(m){
  if(!m||typeof m!=='object'||Array.isArray(m))throw new Error('INVALID_METADATA');
  if(m.schema_version!=='1.0')throw new Error('INVALID_SCHEMA_VERSION');
  for(const field of ['case_id','capture_session_id'])
    if(typeof m[field]!=='string'||!m[field].trim()||m[field].length>128)throw new Error('INVALID_'+field.toUpperCase());
  if(!['checkout','return'].includes(m.capture_phase))throw new Error('INVALID_CAPTURE_PHASE');
  if(!rules.shot_types.includes(m.shot_type))throw new Error('INVALID_SHOT_TYPE');
  if(!rules.vehicle_types.includes(m.vehicle_type))throw new Error('INVALID_VEHICLE_TYPE');
  if(m.shot_type.startsWith('interior_')&&!['left','right'].includes(m.entry_side))throw new Error('ENTRY_SIDE_REQUIRED');
  if(m.shot_type.startsWith('exterior_')&&m.entry_side!=null)throw new Error('ENTRY_SIDE_NOT_APPLICABLE');
  if(!Number.isSafeInteger(m.frame_id)||m.frame_id<0)throw new Error('INVALID_FRAME_ID');
  if(!['preview','final'].includes(m.mode))throw new Error('INVALID_MODE');
  if(m.image_mirrored!==false)throw new Error('UNMIRROR_IMAGE_FIRST');
  if(m.source!=='camera_raw')throw new Error('RAW_CAMERA_IMAGE_REQUIRED');
  return m;
}

function envelope(m,requestId,quality,code,checks,{geometry=null,canCapture=false,qualityPassed=canCapture,
  issueCode=code,reviewRequired=false,manualReviewRemainingMs=null,status='needs_reshoot',action='reshoot',
  image=null,modelVersion=null,latencyMs=null,rulesVersion=rules.version}={}){
  return {schema_version:'1.0',request_id:requestId,case_id:m.case_id,capture_session_id:m.capture_session_id,
    capture_phase:m.capture_phase,shot_type:m.shot_type,vehicle_type:m.vehicle_type,entry_side:m.entry_side??null,
    frame_id:m.frame_id,mode:m.mode,status,capture_quality:{passed:qualityPassed,issues:issueCode==='READY'?[]:[issueCode],
      primary_issue:issueCode==='READY'?null:issueCode,failed_level:checks.L1==='fail'?'L1':checks.L2==='fail'?'L2':geometry?.failed_level??null,
      confidence:null,checks,measurements:quality?.measurements??null},
    guidance:{code,message:messages[code]||'目前無法確認構圖，請依示意圖調整。',
      can_capture:canCapture,review_required:reviewRequired,manual_review_remaining_ms:manualReviewRemainingMs},
    recommended_action:action,geometry:geometry?{suggested_slot:geometry.suggested_slot??null,
      requested_template_matches:geometry.requested_template_matches??null,match_gap:geometry.match_gap??null,
      calibration_status:geometry.calibration_status}:null,
    image:image?{width:image.width,height:image.height,format:image.format,sha256:image.sha256}:null,
    versions:{model:modelVersion,rules:rulesVersion,quality:quality?.version??null,service:'0.1.0'},latency_ms:latencyMs};
}

async function analyzeCapture({metadata,imageBuffer,decoded,detector,tracker=new StabilityTracker(),
  now=()=>Date.now(),config=rules}){
  const m=validateMetadata(metadata),start=now(),requestId=randomUUID();
  const token=tracker.begin(m,start);
  if(token.stale){const error=new Error('STALE_FRAME');error.status=409;throw error;}
  const image={width:decoded.width,height:decoded.height,format:decoded.format,
    sha256:createHash('sha256').update(imageBuffer).digest('hex')};
  let quality=analyzeQuality(decoded);const checks={...quality.checks,L3:'not_evaluated',L4:'not_evaluated',L5:'not_evaluated'};
  const common={image,modelVersion:detector.modelVersion||null,rulesVersion:config.version};
  const stop=(code,opts={})=>{tracker.finish(m,token,false,now());
    return envelope(m,requestId,quality,code,checks,{...common,...opts,latencyMs:now()-start});};
  if(checks.L1==='fail')return stop(quality.flags.includes('TOO_DARK')?'TOO_DARK':'OVEREXPOSED');
  if(checks.L2!=='pass')return stop(checks.L2==='unknown'?'LOW_DETAIL':'BLUR',
    checks.L2==='unknown'?{status:'needs_review',action:'human_review'}:{});
  const predicted=await detector.analyze(imageBuffer);
  if(!predicted||!Array.isArray(predicted.detections))throw new Error('INVALID_MODEL_OUTPUT');
  if(predicted.width!==decoded.width||predicted.height!==decoded.height)throw new Error('INCONSISTENT_IMAGE_ORIENTATION');
  const cars=predicted.detections.filter(d=>d.class_id===0&&d.confidence>=config.thresholds.detection_confidence);
  if(cars.length===1&&Array.isArray(cars[0].box)&&cars[0].box.length===4&&
     cars[0].box.every(v=>Number.isFinite(v)&&v>=0&&v<=1)&&
     cars[0].box[2]>cars[0].box[0]&&cars[0].box[3]>cars[0].box[1]){
    quality=analyzeQuality(decoded,cars[0].box);Object.assign(checks,quality.checks);
    if(checks.L1==='fail')return stop('BACKLIT');
  }
  const geometry=analyzeGeometry({vehicle_type:m.vehicle_type,shot_type:m.shot_type,entry_side:m.entry_side,
    coordinate_space:config.coordinate_space,image_mirrored:false,source:'camera_raw',
    detections:predicted.detections},config);
  Object.assign(checks,geometry.checks);
  if(!geometry.geometry_passed){
    const hasSubject=geometry.checks.L3==='pass'||
      (m.shot_type==='interior_front'&&m.entry_side==='right'&&geometry.code==='FRONT_SEAT_EVIDENCE_UNAVAILABLE')||
      (m.shot_type.startsWith('interior_')&&predicted.detections.some(d=>
        d.confidence>=config.thresholds.detection_confidence&&
        d.class_id===(m.shot_type==='interior_rear'?3:4)));
    const alignmentIssue=['OFF_CENTER','MISSING_REQUIRED_FEATURE','GEOMETRY_MISMATCH',
      'AMBIGUOUS_TEMPLATES','TEMPLATE_NOT_CALIBRATED','FRONT_SEAT_EVIDENCE_UNAVAILABLE'].includes(geometry.code);
    const timing=tracker.manualTiming(token,now());
    if(hasSubject&&alignmentIssue&&timing.available){
      tracker.finish(m,token,false,now());
      return envelope(m,requestId,quality,'MANUAL_REVIEW_AVAILABLE',checks,{...common,geometry,
        issueCode:geometry.code,canCapture:true,qualityPassed:false,reviewRequired:true,
        manualReviewRemainingMs:0,status:m.mode==='final'?'needs_review':'manual_capture_available',
        action:'human_review',latencyMs:now()-start});
    }
    return stop(geometry.code,{geometry,manualReviewRemainingMs:hasSubject&&alignmentIssue?
      timing.remaining_ms:null});
  }
  const stable=tracker.finish(m,token,true,now());
  if(!stable)return envelope(m,requestId,quality,'STABILIZING',checks,
    {...common,geometry,status:'hold',action:'hold',latencyMs:now()-start});
  return envelope(m,requestId,quality,'READY',checks,
    {...common,geometry,canCapture:true,status:'ready',action:'pass',latencyMs:now()-start});
}

module.exports={analyzeCapture,validateMetadata,StabilityTracker,messages};
