// One instanced GPU draw for the entire connection field. Geometry stays on the
// GPU; compact curve control points and signal progress are uploaded each frame.
export class ConnectionRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    const gl = canvas.getContext('webgl2', {alpha: false, antialias: false, depth: false, stencil: false, preserveDrawingBuffer: true});
    if (!gl) throw new Error('WebGL2 unavailable');
    this.gl = gl;
    const vertex = `#version 300 es
      precision highp float;
      layout(location=0) in vec4 endpoints;
      layout(location=2) in vec4 shape;
      layout(location=1) in vec4 signal;

      uniform vec2 viewport;
      uniform vec2 pan;
      uniform float hoverStrength;
      uniform float zoom, segments, brightness, quiet, glow, signalWidth;
      out float across;
      out float along;
      out vec2 screenPosition;
      flat out float progress;
      flat out float highlight;
      flat out float kind;
      flat out float routeProgress;
      flat out float routeAlpha;
      void main(){
        vec2 a=endpoints.xy,b=endpoints.zw;
        vec2 c=a+shape.xy,d=b-shape.xy;
        float t=float(gl_VertexID/2)/segments, u=1.-t;
        vec2 p=u*u*u*a+3.*u*u*t*c+3.*u*t*t*d+t*t*t*b;
        vec2 tangent=3.*u*u*(c-a)+6.*u*t*(d-c)+3.*t*t*(b-d);
        vec2 normal=normalize(vec2(-tangent.y,tangent.x)+vec2(.00001));
        float side=gl_VertexID%2==0?-1.:1.;
        bool localPulse=signal.x>=0.&&signal.x<1.22;
        bool lit=localPulse||signal.y>0.||signal.w>0.;
        float swell=exp(-pow((t-signal.z)/.23,2.))*signal.w;
        float radius=lit?1.4+4.*glow+signalWidth*(localPulse?1.:0.)+signalWidth*1.3*swell:1.4;
        vec2 screen=p*zoom+pan+normal*side*radius;
        if(!lit&&quiet*brightness==0.&&hoverStrength==0.)screen=vec2(-100.);
        gl_Position=vec4(screen/viewport*vec2(2.,-2.)+vec2(-1.,1.),0.,1.);
        screenPosition=p*zoom+pan;across=side*radius;along=t;progress=signal.x;highlight=signal.y;kind=shape.z;routeProgress=signal.z;routeAlpha=signal.w;
      }`;
    const fragment = `#version 300 es
      precision highp float;
      in float across;
      in float along;
      in vec2 screenPosition;
      flat in float progress;
      flat in float highlight;
      flat in float kind;
      flat in float routeProgress;
      flat in float routeAlpha;
      uniform vec3 primaryColor, secondaryColor;
      uniform vec2 mouse;
      uniform float hoverRadius, hoverStrength;
      uniform float brightness, glow, quiet, fullLength, light, signalWidth;
      out vec4 color;
      void main(){
        float distance=abs(across);
        float core=exp(-distance*distance*3.5);
        float halo=exp(-distance*distance*.24);
        float isActive=step(0.,progress)*step(progress,1.22);
        float strength=sin(clamp(progress/1.22,0.,1.)*3.14159265)*isActive;
        float tail=smoothstep(progress-.25,progress-.06,along)*(1.-smoothstep(progress-.01,progress+.008,along))*isActive;
        float head=exp(-pow((along-progress)*90.,2.))*isActive;
        float base=quiet*brightness*(mix(.31,.23,light)*core+.025*glow*halo);
        float charge=fullLength*strength*(mix(.66,.43,light)*core+.10*glow*halo);
        float pulseCore=exp(-pow(distance/max(.5,signalWidth),2.)*3.5);
        float pulse=tail*(.68*pulseCore+.12*glow*halo)+head*(.35*pulseCore+.12*glow*halo);
        float swell=exp(-pow((along-routeProgress)/.23,2.));
        float routeCore=exp(-pow(distance/(.65+signalWidth*1.25*swell),2.)*2.);
        float route=routeAlpha*(.82*routeCore+.08*glow*halo);
        float proximity=pow(max(0.,1.-length(screenPosition-mouse)/hoverRadius),2.)*hoverStrength;
        float focus=proximity*(.7*core+.12*halo);
        float alpha=clamp(base+charge+pulse+route+focus+highlight*.65*core,0.,.95);
        if(alpha<.003)discard;
        color=vec4(mix(primaryColor,secondaryColor,kind*(1.-routeAlpha)),alpha);
      }`;
    const compile = (type, source) => {
      const shader = gl.createShader(type);gl.shaderSource(shader, source);gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {const message=gl.getShaderInfoLog(shader);gl.deleteShader(shader);throw new Error(message);}
      return shader;
    };
    const vs=compile(gl.VERTEX_SHADER,vertex),fs=compile(gl.FRAGMENT_SHADER,fragment);
    const program=gl.createProgram();gl.attachShader(program,vs);gl.attachShader(program,fs);gl.linkProgram(program);gl.deleteShader(vs);gl.deleteShader(fs);
    if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(program));
    this.program=program;gl.useProgram(program);this.uniforms={};
    for(const name of ['viewport','pan','zoom','segments','primaryColor','secondaryColor','brightness','glow','quiet','fullLength','light','signalWidth','mouse','hoverRadius','hoverStrength'])this.uniforms[name]=gl.getUniformLocation(program,name);
    this.vao=gl.createVertexArray();gl.bindVertexArray(this.vao);
    this.edges=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,this.edges);gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,4,gl.FLOAT,false,32,0);gl.vertexAttribDivisor(0,1);gl.enableVertexAttribArray(2);gl.vertexAttribPointer(2,4,gl.FLOAT,false,32,16);gl.vertexAttribDivisor(2,1);
    this.signals=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,this.signals);gl.enableVertexAttribArray(1);gl.vertexAttribPointer(1,4,gl.FLOAT,false,0,0);gl.vertexAttribDivisor(1,1);
    gl.disable(gl.DEPTH_TEST);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);

  }
  setEdges(edges) {
    const gl=this.gl;this.topology=edges;
    this.count=edges.length;this.signalData=new Float32Array(edges.length*4);this.geometry=new Float32Array(edges.length*8);
    gl.bindBuffer(gl.ARRAY_BUFFER,this.edges);gl.bufferData(gl.ARRAY_BUFFER,this.geometry.byteLength,gl.DYNAMIC_DRAW);
    gl.bindBuffer(gl.ARRAY_BUFFER,this.signals);gl.bufferData(gl.ARRAY_BUFFER,this.signalData.byteLength,gl.DYNAMIC_DRAW);
  }
  draw(nodes, state, camera, palette, time, width, height, dpr, cursor) {
    const gl=this.gl,u=this.uniforms;
    if(gl.isContextLost())return;
    if(this.canvas.width!==Math.round(width*dpr)||this.canvas.height!==Math.round(height*dpr)){this.canvas.width=Math.round(width*dpr);this.canvas.height=Math.round(height*dpr);}
    gl.viewport(0,0,this.canvas.width,this.canvas.height);
    const rgb=hex=>[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255);
    gl.clearColor(...rgb(palette.bg),1);gl.clear(gl.COLOR_BUFFER_BIT);gl.useProgram(this.program);gl.bindVertexArray(this.vao);
    for(let i=0;i<this.count;i++){
      const e=this.topology[i],a=nodes[e.from],b=nodes[e.to],offset=i*8;
      this.geometry[offset]=a.x;this.geometry[offset+1]=a.y;this.geometry[offset+2]=b.x;this.geometry[offset+3]=b.y;
      this.geometry[offset+4]=(b.x-a.x)*.46;this.geometry[offset+5]=Math.sin(time*.75+e.l*.6+e.bend*2)*state.motion*17*state.scaleY;this.geometry[offset+6]=e.color;
    }
    gl.bindBuffer(gl.ARRAY_BUFFER,this.edges);gl.bufferSubData(gl.ARRAY_BUFFER,0,this.geometry);
    gl.bindBuffer(gl.ARRAY_BUFFER,this.signals);gl.bufferSubData(gl.ARRAY_BUFFER,0,this.signalData);
    gl.uniform2f(u.mouse,cursor.x,cursor.y);gl.uniform1f(u.hoverRadius,state.hoverRadius);gl.uniform1f(u.hoverStrength,cursor.active&&state.hoverMode!=='off'?state.hoverStrength:0);
    gl.uniform2f(u.viewport,width,height);gl.uniform2f(u.pan,camera.x,camera.y);gl.uniform1f(u.zoom,camera.zoom);const segments=camera.zoom>1.5?32:16;gl.uniform1f(u.segments,segments);
    gl.uniform3fv(u.primaryColor,rgb(palette.purple));gl.uniform3fv(u.secondaryColor,rgb(palette.amber));
    for(const key of ['brightness','glow','quiet','fullLength','signalWidth'])gl.uniform1f(u[key],Number(state[key]));gl.uniform1f(u.light,state.theme==='light'?1:0);
    gl.drawArraysInstanced(gl.TRIANGLE_STRIP,0,(segments+1)*2,this.count);
  }
}
