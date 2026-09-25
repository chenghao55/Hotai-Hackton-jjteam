'use strict';

const {spawn}=require('node:child_process');
const path=require('node:path');
const os=require('node:os');
const fs=require('node:fs');
const {randomUUID,createHash}=require('node:crypto');

class InferenceError extends Error {
  constructor(code) { super(code); this.code=code; }
}

class YoloClient {
  constructor({python=process.env.CAPTURE_PYTHON||(
    fs.existsSync(path.join(__dirname,'../.venv/Scripts/python.exe'))
      ? path.join(__dirname,'../.venv/Scripts/python.exe') : 'python'),
    modelPath=process.env.CAPTURE_MODEL_PATH||path.join(os.homedir(),'Downloads','best.pt'),
    timeoutMs=10000}={}) {
    this.python=python;this.modelPath=modelPath;this.timeoutMs=timeoutMs;
    this.ready=false;this.process=null;this.buffer='';this.pending=null;this.queue=[];this.reason='MODEL_NOT_STARTED';this.modelVersion=null;
  }
  start() {
    if(this.process) return;
    if(!fs.existsSync(this.modelPath)){this.reason='MODEL_FILE_MISSING';return;}
    this.modelVersion='best-'+createHash('sha256').update(fs.readFileSync(this.modelPath)).digest('hex').slice(0,12);
    fs.mkdirSync(path.join(__dirname,'../.runtime/config'),{recursive:true});
    fs.mkdirSync(path.join(__dirname,'../.runtime/matplotlib'),{recursive:true});
    this.reason='MODEL_STARTING';
    const child=spawn(this.python,['-u',path.join(__dirname,'yolo_worker.py')],{
      stdio:['pipe','pipe','pipe'],windowsHide:true,
      env:{...process.env,CAPTURE_MODEL_PATH:this.modelPath,
        YOLO_CONFIG_DIR:process.env.YOLO_CONFIG_DIR||path.join(__dirname,'../.runtime/config'),
        MPLCONFIGDIR:process.env.MPLCONFIGDIR||path.join(__dirname,'../.runtime/matplotlib')}});
    this.process=child;
    child.stdout.setEncoding('utf8');
    child.stdout.on('data',chunk=>this.onData(chunk));
    child.stderr.on('data',()=>{}); // Do not log image data or model paths.
    child.on('error',()=>this.onExit('PYTHON_UNAVAILABLE'));
    child.on('exit',()=>this.onExit('MODEL_WORKER_EXITED'));
  }
  onExit(code) {
    this.ready=false;this.reason=this.reason==='MODEL_LOAD_FAILED'||this.reason==='MODEL_CLASSES_MISMATCH'?this.reason:code;this.process=null;
    if(this.pending){clearTimeout(this.pending.timer);this.pending.reject(new InferenceError(code));this.pending=null;}
    for(const job of this.queue)job.reject(new InferenceError(code));
    this.queue=[];
  }
  onData(chunk) {
    this.buffer+=chunk;
    if(this.buffer.length>32*1024*1024){this.process?.kill();return;}
    let e;
    while((e=this.buffer.indexOf('\n'))>=0){
      const raw=this.buffer.slice(0,e);this.buffer=this.buffer.slice(e+1);
      let message;try{message=JSON.parse(raw);}catch{continue;}
      if(message.type==='ready'){this.ready=true;this.reason=null;this.pump();continue;}
      if(message.type==='unavailable'){this.reason=message.code||'MODEL_LOAD_FAILED';this.process?.kill();continue;}
      if(!this.pending||message.id!==this.pending.id)continue;
      const job=this.pending;this.pending=null;clearTimeout(job.timer);
      if(message.type==='result')job.resolve(message);
      else job.reject(new InferenceError(message.code||'INFERENCE_FAILED'));
      this.pump();
    }
  }
  pump() {
    if(!this.ready||this.pending||!this.queue.length)return;
    const job=this.queue.shift();this.pending=job;
    job.timer=setTimeout(()=>{this.process?.kill();},this.timeoutMs);
    try{this.process.stdin.write(JSON.stringify({id:job.id,image_base64:job.buffer.toString('base64')})+'\n');}
    catch{this.process?.kill();}
  }
  analyze(buffer) {
    if(!this.process)this.start();
    if(!this.ready)throw new InferenceError(this.reason||'MODEL_NOT_READY');
    if(this.queue.length>=1)throw new InferenceError('MODEL_BUSY');
    return new Promise((resolve,reject)=>{this.queue.push({id:randomUUID(),buffer,resolve,reject,timer:null});this.pump();});
  }
  close(){this.process?.kill();}
}
module.exports={YoloClient,InferenceError};
