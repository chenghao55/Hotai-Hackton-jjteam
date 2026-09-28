'use strict';

const http=require('node:http');
const {decodeImage,ImageError}=require('./image-decode.cjs');
const {analyzeCapture,validateMetadata,StabilityTracker}=require('./capture-decision.cjs');
const {YoloClient,InferenceError}=require('./yolo-client.cjs');
const {defaults:rules}=require('./capture-geometry.cjs');
const {randomUUID}=require('node:crypto');

const MAX_BODY=11*1024*1024;
function apiError(status,code,retryable=false){const e=new Error(code);e.status=status;e.retryable=retryable;return e;}
async function readBody(request){
  const chunks=[];let total=0;
  for await(const chunk of request){total+=chunk.length;if(total>MAX_BODY)throw apiError(413,'PAYLOAD_TOO_LARGE');chunks.push(chunk);}
  return Buffer.concat(chunks);
}
async function parseMultipart(body,contentType){
  if(!/^multipart\/form-data;\s*boundary=/i.test(contentType))throw apiError(415,'MULTIPART_REQUIRED');
  let form;
  try{form=await new Request('http://localhost/upload',{method:'POST',headers:{'content-type':contentType},body}).formData();}
  catch{throw apiError(422,'INVALID_MULTIPART');}
  const file=form.get('image'),raw=form.get('metadata');
  if(!file||typeof file==='string')throw apiError(422,'IMAGE_REQUIRED');
  if(!['image/jpeg','image/png'].includes(file.type))throw apiError(415,'UNSUPPORTED_IMAGE_FORMAT');
  if(file.size>10*1024*1024)throw apiError(413,'IMAGE_TOO_LARGE');
  if(typeof raw!=='string')throw apiError(422,'METADATA_REQUIRED');
  let metadata;
  try{metadata=JSON.parse(raw);}catch{throw apiError(422,'INVALID_METADATA_JSON');}
  return {metadata,imageBuffer:Buffer.from(await file.arrayBuffer())};
}
function createServer({detector=new YoloClient(),tracker=new StabilityTracker()}={}){
  detector.start?.();
  const server=http.createServer(async(request,response)=>{
    const requestId=randomUUID();
    const send=(status,data)=>{if(response.writableEnded)return;response.writeHead(status,
      {'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});
      response.end(JSON.stringify(data));};
    try{
      const url=new URL(request.url,'http://localhost');
      if(request.method==='GET'&&url.pathname==='/health')return send(200,{status:'alive'});
      if(request.method==='GET'&&url.pathname==='/ready')return send(detector.ready?200:503,
        {ready:!!detector.ready,code:detector.ready?'READY':detector.reason||'MODEL_NOT_READY',
          model_version:detector.modelVersion||null,service_classes:rules.model_classes});
      if(request.method!=='POST'||url.pathname!=='/api/v1/capture/analyze')return send(404,{request_id:requestId,code:'NOT_FOUND'});
      const body=await readBody(request);
      const {metadata,imageBuffer}=await parseMultipart(body,request.headers['content-type']||'');
      try{validateMetadata(metadata);}catch(e){throw apiError(422,e.message);}
      const decoded=decodeImage(imageBuffer);
      const result=await analyzeCapture({metadata,imageBuffer,decoded,detector,tracker});
      return send(200,result);
    }catch(error){
      const status=error.status||(error instanceof ImageError?error.status:
        error instanceof InferenceError?(error.code==='MODEL_BUSY'?429:503):500);
      const code=error.code||error.message||'INTERNAL_ERROR';
      return send(status,{request_id:requestId,code:status===500?'INTERNAL_ERROR':code,
        message:status===500?'服務暫時無法分析照片。':errorMessage(code),
        retryable:error.retryable??[429,500,503].includes(status)});
    }
  });
  server.on('close',()=>detector.close?.());
  return server;
}
function errorMessage(code){
  const map={PAYLOAD_TOO_LARGE:'照片上傳資料過大，請縮小後重試。',IMAGE_TOO_LARGE:'照片檔案超過 10 MB。',
    IMAGE_DIMENSIONS_EXCEEDED:'照片解析度超過 2000 萬畫素。',UNSUPPORTED_IMAGE_FORMAT:'請上傳 JPEG 或 PNG 照片。',
    INVALID_IMAGE:'照片無法解碼，請重新拍攝。',STALE_FRAME:'這是較舊的預覽影格，請改用最新畫面。',
    TRANSPARENT_IMAGE_UNSUPPORTED:'請使用相機拍攝的非透明原始照片。',
    MODEL_BUSY:'目前分析量過大，請稍後重試。',MODEL_NOT_READY:'模型尚未就緒，請稍後重試。',
    MODEL_FILE_MISSING:'模型檔案未設定，請聯絡管理員。'};
  return map[code]||'請檢查照片與拍攝欄位後重試。';
}
if(require.main===module){
  const host=process.env.CAPTURE_HOST||'127.0.0.1',port=Number(process.env.CAPTURE_PORT||8080);
  createServer().listen(port,host,()=>console.log(`Capture API listening on http://${host}:${port}`));
}
module.exports={createServer,parseMultipart,readBody,apiError};
