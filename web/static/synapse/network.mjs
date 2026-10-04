export function random(seed = 42) {
  return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}
export function dataset(kind, count = 240, noise = .05, seed = 81) {
  const r = random(seed), points = [];
  for (let i = 0; i < count; i++) {
    let x, y, label;
    if (kind === 'spiral') {
      label = i % 2; const t = r(), angle = t * Math.PI * 2 + label * Math.PI;
      x = Math.cos(angle) * t * .88; y = Math.sin(angle) * t * .88;
    } else {
      x = r() * 1.9 - .95; y = r() * 1.9 - .95;
      label = kind === 'circle' ? +(x*x + y*y > .55) : kind === 'xor' ? +(x*y > 0) : +(y > x * .65 + .1);
    }
    x += (r() - .5) * noise * 2; y += (r() - .5) * noise * 2;
    points.push({x: [x, y], y: label});
  }
  return points;
}
const sigmoid = x => 1 / (1 + Math.exp(-Math.max(-500, Math.min(500, x))));
export class Network {
  constructor(sizes = [2,6,5,4,1], activation = 'tanh', seed = 42) {
    this.sizes = [...sizes]; this.activation = activation; this.epochs = 0;
    const r = random(seed); this.r = r;
    this.weights = sizes.slice(1).map((n,l) => Array.from({length:n}, () => Array.from({length:sizes[l]}, () => (r()*2-1)*Math.sqrt(6/(sizes[l]+n)))));
    this.biases = sizes.slice(1).map(n => Array(n).fill(0));
  }
  activate(z) { return this.activation === 'relu' ? Math.max(0,z) : this.activation === 'sigmoid' ? sigmoid(z) : Math.tanh(z); }
  derivative(a) { return this.activation === 'relu' ? +(a > 0) : this.activation === 'sigmoid' ? a*(1-a) : 1-a*a; }
  forward(input) {
    const acts = [[...input]];
    this.weights.forEach((layer,l) => acts.push(layer.map((weights,j) => { const z = weights.reduce((s,w,k) => s+w*acts[l][k],this.biases[l][j]); return l === this.weights.length-1 ? sigmoid(z) : this.activate(z); })));
    return acts;
  }
  predict(input) { return this.forward(input).at(-1)[0]; }
  evaluate(data) {
    let loss = 0, correct = 0;
    for (const p of data) {const a = this.predict(p.x), q = Math.max(1e-12,Math.min(1-1e-12,a)); loss -= p.y*Math.log(q)+(1-p.y)*Math.log(1-q); correct += +(+(a>=.5) === p.y);}
    return {loss:loss/data.length,accuracy:correct/data.length*100};
  }
  trainEpoch(data, rate = .03, batchSize = 32) {
    const shuffled = [...data];
    for(let i=shuffled.length-1;i>0;i--){const j=Math.floor(this.r()*(i+1)); [shuffled[i],shuffled[j]]=[shuffled[j],shuffled[i]];}
    for(let start=0;start<shuffled.length;start+=batchSize){
      const batch=shuffled.slice(start,start+batchSize);
      const dw=this.weights.map(layer=>layer.map(row=>row.map(()=>0))), db=this.biases.map(row=>row.map(()=>0));
      for(const point of batch){
        const a=this.forward(point.x); let delta=[a.at(-1)[0]-point.y];
        for(let l=this.weights.length-1;l>=0;l--){
          for(let j=0;j<delta.length;j++){db[l][j]+=delta[j]; for(let k=0;k<a[l].length;k++)dw[l][j][k]+=delta[j]*a[l][k];}
          if(l>0)delta=a[l].map((v,k)=>this.weights[l].reduce((s,row,j)=>s+row[k]*delta[j],0)*this.derivative(v));
        }
      }
      this.weights.forEach((layer,l)=>layer.forEach((row,j)=>{this.biases[l][j]-=rate*db[l][j]/batch.length;row.forEach((_,k)=>{row[k]-=rate*dw[l][j][k]/batch.length;});}));
    }
    this.epochs++;
  }
  get parameterCount(){return this.weights.reduce((s,l)=>s+l.reduce((n,r)=>n+r.length+1,0),0);}
  toJSON(){return {format:'synapse-network',version:1,sizes:this.sizes,activation:this.activation,epochs:this.epochs,weights:this.weights,biases:this.biases};}
}
