'use strict';
const fs=require('node:fs/promises');
const path=require('node:path');
const file=process.argv[2];
if(!file){console.error('Usage: node examples/send-photo.cjs <photo.jpg|photo.png>');process.exit(2);}
const ext=path.extname(file).toLowerCase();
const mime=ext==='.png'?'image/png':ext==='.jpg'||ext==='.jpeg'?'image/jpeg':null;
if(!mime){console.error('JPEG or PNG only');process.exit(2);}
async function main(){
  const metadata={schema_version:'1.0',case_id:'DEMO-001',capture_session_id:'DEMO-SESSION-001',
    capture_phase:'checkout',shot_type:'exterior_front_left',vehicle_type:'sedan',frame_id:1,
    mode:'final',image_mirrored:false,source:'camera_raw'};
  const form=new FormData();form.append('metadata',JSON.stringify(metadata));
  form.append('image',new Blob([await fs.readFile(file)],{type:mime}),path.basename(file));
  const response=await fetch(process.env.CAPTURE_URL||'http://127.0.0.1:8080/api/v1/capture/analyze',
    {method:'POST',body:form});
  console.log(response.status,JSON.stringify(await response.json(),null,2));
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
