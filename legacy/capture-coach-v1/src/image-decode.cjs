'use strict';

const jpeg = require('jpeg-js');
const {PNG} = require('pngjs');

class ImageError extends Error {
  constructor(code, status) { super(code); this.code = code; this.status = status; }
}

function sniffImage(buffer) {
  if (buffer.length >= 8 && buffer.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10]))) return 'png';
  if (buffer.length >= 3 && buffer[0] === 255 && buffer[1] === 216 && buffer[2] === 255) return 'jpeg';
  throw new ImageError('UNSUPPORTED_IMAGE_FORMAT', 415);
}

function jpegDimensions(buffer) {
  let pos = 2;
  while (pos + 4 <= buffer.length) {
    if (buffer[pos++] !== 255) continue;
    let marker = buffer[pos++];
    while (marker === 255 && pos < buffer.length) marker = buffer[pos++];
    if (marker === 216 || marker === 1) continue;
    if (marker === 217 || marker === 218) break;
    if (pos + 2 > buffer.length) break;
    const length = buffer.readUInt16BE(pos);
    if (length < 2 || pos + length > buffer.length) break;
    if ([0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf].includes(marker)) {
      if (length < 7) break;
      return [buffer.readUInt16BE(pos + 3), buffer.readUInt16BE(pos + 5)];
    }
    pos += length;
  }
  throw new ImageError('INVALID_IMAGE', 422);
}

function dimensions(buffer, format) {
  if (format === 'jpeg') return jpegDimensions(buffer);
  if (buffer.length < 24 || buffer.toString('ascii', 12, 16) !== 'IHDR') throw new ImageError('INVALID_IMAGE', 422);
  return [buffer.readUInt32BE(16), buffer.readUInt32BE(20)];
}

function jpegOrientation(buffer) {
  let pos=2;
  while(pos+4<=buffer.length){
    if(buffer[pos++]!==255)continue;
    let marker=buffer[pos++];while(marker===255&&pos<buffer.length)marker=buffer[pos++];
    if(marker===217||marker===218)break;
    if(marker===216||marker===1)continue;
    if(pos+2>buffer.length)break;
    const length=buffer.readUInt16BE(pos),end=pos+length;
    if(length<2||end>buffer.length)break;
    if(marker===225&&length>=16&&buffer.toString('ascii',pos+2,pos+6)==='Exif'){
      const t=pos+8;
      if(t+8<=end){
        const little=buffer.toString('ascii',t,t+2)==='II';
        const big=buffer.toString('ascii',t,t+2)==='MM';
        if(little||big){
          const u16=i=>little?buffer.readUInt16LE(i):buffer.readUInt16BE(i);
          const u32=i=>little?buffer.readUInt32LE(i):buffer.readUInt32BE(i);
          if(u16(t+2)===42){
            const ifd=t+u32(t+4);
            if(ifd+2<=end){
              const count=Math.min(u16(ifd),256);
              for(let i=0;i<count;i++){
                const p=ifd+2+i*12;if(p+12>end)break;
                if(u16(p)===0x112&&u16(p+2)===3&&u32(p+4)===1){
                  const value=u16(p+8);return value>=1&&value<=8?value:1;
                }
              }
            }
          }
        }
      }
    }
    pos=end;
  }
  return 1;
}

function orientPixels(data,width,height,orientation){
  if(orientation===1)return {width,height,data};
  const swap=orientation>=5,tw=swap?height:width,th=swap?width:height;
  const out=Buffer.allocUnsafe(data.length);
  for(let y=0;y<th;y++)for(let x=0;x<tw;x++){
    let sx=x,sy=y;
    if(orientation===2)sx=width-1-x;
    else if(orientation===3){sx=width-1-x;sy=height-1-y;}
    else if(orientation===4)sy=height-1-y;
    else if(orientation===5){sx=y;sy=x;}
    else if(orientation===6){sx=y;sy=height-1-x;}
    else if(orientation===7){sx=width-1-y;sy=height-1-x;}
    else if(orientation===8){sx=width-1-y;sy=x;}
    const from=(sy*width+sx)*4,to=(y*tw+x)*4;
    out[to]=data[from];out[to+1]=data[from+1];out[to+2]=data[from+2];out[to+3]=data[from+3];
  }
  return {width:tw,height:th,data:out};
}

function decodeImage(buffer, {maxBytes = 10 * 1024 * 1024, maxPixels = 20_000_000} = {}) {
  if (!Buffer.isBuffer(buffer) || !buffer.length) throw new ImageError('EMPTY_IMAGE', 422);
  if (buffer.length > maxBytes) throw new ImageError('IMAGE_TOO_LARGE', 413);
  const format = sniffImage(buffer);
  const [width, height] = dimensions(buffer, format);
  if (!width || !height || width * height > maxPixels) throw new ImageError('IMAGE_DIMENSIONS_EXCEEDED', 413);
  try {
    const decoded = format === 'jpeg'
      ? jpeg.decode(buffer, {useTArray:true, formatAsRGBA:true, maxResolutionInMP:21, maxMemoryUsageInMB:256})
      : PNG.sync.read(buffer, {skipRescale:true});
    if (decoded.width !== width || decoded.height !== height || decoded.data.length !== width * height * 4)
      throw new Error('decoded dimensions mismatch');
    if(format==='png')for(let i=3;i<decoded.data.length;i+=4)
      if(decoded.data[i]!==255)throw new ImageError('TRANSPARENT_IMAGE_UNSUPPORTED',415);
    const orientation=format==='jpeg'?jpegOrientation(buffer):1;
    return {format,orientation,...orientPixels(decoded.data,width,height,orientation)};
  } catch(error) {
    if(error instanceof ImageError)throw error;
    throw new ImageError('INVALID_IMAGE', 422);
  }
}

module.exports = {decodeImage, ImageError, sniffImage,jpegOrientation,orientPixels};
