'use strict';

// Conservative draft thresholds. Results require calibration on labelled real photos.
const VERSION = 'photo-quality-v0.1-draft';
function sample(image,region=[0,0,1,1]){
  const n = 128, grey = new Float64Array(n*n), d = image.data;
  let sum=0, dark=0, bright=0;
  for (let y=0;y<n;y++) for (let x=0;x<n;x++) {
    const sx=Math.min(image.width-1,Math.floor((region[0]+(x+0.5)*(region[2]-region[0])/n)*image.width));
    const sy=Math.min(image.height-1,Math.floor((region[1]+(y+0.5)*(region[3]-region[1])/n)*image.height));
    const i=(sy*image.width+sx)*4;
    const v=0.2126*d[i]+0.7152*d[i+1]+0.0722*d[i+2];
    grey[y*n+x]=v;sum+=v;if(v<40)dark++;if(v>245)bright++;
  }
  const mean=sum/(n*n), darkFraction=dark/(n*n), brightFraction=bright/(n*n);
  let lapSum=0,lapSquares=0,count=0;
  for(let y=1;y<n-1;y++)for(let x=1;x<n-1;x++){
    const i=y*n+x;
    const lap=4*grey[i]-grey[i-1]-grey[i+1]-grey[i-n]-grey[i+n];
    lapSum+=lap;lapSquares+=lap*lap;count++;
  }
  const sharpness=Math.max(0,lapSquares/count-(lapSum/count)**2);
  return {mean,darkFraction,brightFraction,sharpness};
}
function analyzeQuality(image,subjectBox=null) {
  const {mean,darkFraction,brightFraction,sharpness}=sample(image);
  const subject=subjectBox?sample(image,subjectBox):null;
  const flags=[];
  if(mean<50 && darkFraction>0.65)flags.push('TOO_DARK');
  if(brightFraction>0.78 && mean>225)flags.push('OVEREXPOSED');
  if(subject&&subject.mean<72&&mean-subject.mean>70&&subject.darkFraction>0.42)flags.push('BACKLIT');
  // Very low texture cannot distinguish blur from a plain wall or smooth surface.
  if(sharpness<12)flags.push('LOW_DETAIL');
  else if(sharpness<45)flags.push('BLUR');
  const l1=flags.some(x=>['TOO_DARK','OVEREXPOSED','BACKLIT'].includes(x))?'fail':'pass';
  const l2=flags.includes('BLUR')?'fail':flags.includes('LOW_DETAIL')?'unknown':'pass';
  return {version:VERSION,checks:{L1:l1,L2:l2},flags,
    measurements:{mean_luma:+mean.toFixed(2),dark_fraction:+darkFraction.toFixed(4),
      bright_fraction:+brightFraction.toFixed(4),laplacian_variance:+sharpness.toFixed(2),
      subject_mean_luma:subject?+subject.mean.toFixed(2):null,
      subject_dark_fraction:subject?+subject.darkFraction.toFixed(4):null}};
}
module.exports={analyzeQuality,VERSION};
