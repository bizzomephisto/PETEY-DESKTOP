// Route launches are scheduled in simulation time, independent of rendering FPS.
export class SignalRoutes {
  constructor(edges, layers, neurons, random, now = 0) {
    this.edges=edges;this.layers=layers;this.neurons=neurons;this.random=random;
    this.interval=1;this.edgeDuration=.28;this.nextLaunch=now+this.interval;
    this.routes=[];this.launched=0;this.completed=0;
    this.outgoing=Array.from({length:layers*neurons},()=>[]);
    edges.forEach((edge,i)=>this.outgoing[edge.from].push(i));
    this.progress=new Float32Array(edges.length);this.strength=new Float32Array(edges.length);
  }
  launch(at) {
    let node=Math.floor(this.random()*this.neurons);const path=[];
    for(let layer=0;layer<this.layers-1;layer++){
      // Prefer nearby neurons so the whole route is visually easy to follow.
      const candidates=[...this.outgoing[node]].sort((a,b)=>Math.abs(this.edges[a].to%this.neurons-node%this.neurons)-Math.abs(this.edges[b].to%this.neurons-node%this.neurons)).slice(0,4);
      if(!candidates.length)return;
      const edge=candidates[Math.floor(this.random()*candidates.length)];path.push(edge);node=this.edges[edge].to;
    }
    this.routes.push({at,path});this.launched++;
  }
  advance(now,chance) {
    while(now>=this.nextLaunch){if(this.random()<chance)this.launch(this.nextLaunch);this.nextLaunch+=this.interval;}
    this.routes=this.routes.filter(route=>{if(now-route.at>route.path.length*this.edgeDuration+.6){this.completed++;return false;}return true;});
  }
  sample(now) {
    this.progress.fill(-100);this.strength.fill(0);
    for(const route of this.routes){
      const elapsed=now-route.at,head=elapsed/this.edgeDuration;
      const alpha=Math.min(1,Math.max(0,elapsed/.2),Math.max(0,(route.path.length*this.edgeDuration+.6-elapsed)/.6));
      route.path.forEach((edge,step)=>{
        const p=head-step;
        // On shared edges, prioritize the wave closest to this edge.
        if(this.strength[edge]===0||Math.abs(p-.5)<Math.abs(this.progress[edge]-.5)){this.progress[edge]=p;this.strength[edge]=alpha;}
      });
    }
    return this;
  }
}
