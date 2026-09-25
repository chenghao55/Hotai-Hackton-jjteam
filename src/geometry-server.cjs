'use strict';
// Internal L3-L5 integration endpoint. It does not accept photos or run YOLO.
const http=require('node:http');
const {analyzeGeometry}=require('./capture-geometry.cjs');
function createServer(){
 return http.createServer((request,response)=>{
  const send=(status,body)=>{if(!response.writableEnded){response.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});response.end(JSON.stringify(body));}};
  if(request.method==='GET'&&request.url==='/health')return send(200,{status:'geometry_only',model_loaded:false});
  if(request.method!=='POST'||request.url!=='/api/v1/capture/geometry')return send(404,{code:'NOT_FOUND'});
  if(!(request.headers['content-type']||'').toLowerCase().startsWith('application/json'))return send(415,{code:'JSON_REQUIRED'});
  let bytes=0,overLimit=false;const chunks=[];
  request.on('data',chunk=>{bytes+=chunk.length;if(bytes>1024*1024){overLimit=true;chunks.length=0;send(413,{code:'PAYLOAD_TOO_LARGE'});return;}if(!overLimit)chunks.push(chunk)});
  request.on('end',()=>{if(overLimit)return;let input;try{input=JSON.parse(Buffer.concat(chunks).toString('utf8'));}catch{return send(400,{code:'INVALID_JSON'});}
   try{const result=analyzeGeometry(input);send(200,{...result,frame_id:input.frame_id??null,capture_session_id:input.capture_session_id??null});}
   catch(error){send(422,{code:error.message});}
  });
  request.on('error',()=>send(400,{code:'REQUEST_INTERRUPTED'}));
 });
}
if(require.main===module)createServer().listen(8081,'127.0.0.1',()=>console.log('Geometry-only API: http://127.0.0.1:8081'));
module.exports={createServer};
