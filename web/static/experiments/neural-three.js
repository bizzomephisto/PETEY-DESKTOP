import {PATTERNS, buildPattern} from './neural-patterns.js';

const stage = document.getElementById('stage');
const canvas = document.getElementById('scene');
const energyInput = document.getElementById('energy');
const energyValue = document.getElementById('energy-value');
const qualityInput = document.getElementById('quality');
const stateLabel = document.getElementById('state-label');
const errorBox = document.getElementById('error');
const fpsLabel = document.getElementById('fps');
const callsLabel = document.getElementById('draw-calls');
const countLabel = document.getElementById('node-count');
const linkCountLabel = document.getElementById('link-count');
const patternName = document.getElementById('pattern-name');
const patternDescription = document.getElementById('pattern-description');
const cycleButton = document.getElementById('cycle');
const micButton = document.getElementById('mic');

const STATES = {
  idle: {label: 'Present', color: 0x56b8ff, secondary: 0x9a78ff, speed: 0.14},
  listening: {label: 'Listening', color: 0xff9b37, secondary: 0xffd176, speed: 0.23},
  thinking: {label: 'Thinking', color: 0x9d73ff, secondary: 0x43bfff, speed: 0.42},
  speaking: {label: 'Speaking', color: 0x3cc7ff, secondary: 0xb3f9ff, speed: 0.32},
  muted: {label: 'Muted', color: 0xc95b65, secondary: 0xff9d7c, speed: 0.06},
};
const DEMO_STATES = ['idle', 'listening', 'thinking', 'speaking'];
const PATTERN_IDS = Object.keys(PATTERNS);

function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = false;
}

async function start() {
  let THREE;
  try {
    THREE = await import('./vendor/three-0.186.0/three.module.js');
  } catch (error) {
    showError(`Three.js could not load: ${error.message}`);
    return;
  }

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({canvas, antialias: true, alpha: true, powerPreference: 'high-performance'});
  } catch (error) {
    showError(`WebGL is unavailable in this browser: ${error.message}`);
    return;
  }
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.setClearColor(0x000000, 0);

  const scene = new THREE.Scene();
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const camera = new THREE.PerspectiveCamera(48, 1, 0.1, 100);
  camera.position.z = 9.5;
  const brain = new THREE.Group();
  scene.add(brain);

  const uniforms = {
    uTime: {value: 0},
    uEnergy: {value: 0.5},
    uPrimary: {value: new THREE.Color(STATES.idle.color)},
    uSecondary: {value: new THREE.Color(STATES.idle.secondary)},
  };
  const pointsMaterial = new THREE.ShaderMaterial({
    uniforms,
    vertexShader: `
      attribute float aSize;
      attribute float aMix;
      uniform float uTime;
      uniform float uEnergy;
      varying float vMix;
      varying float vGlow;
      void main() {
        vMix = aMix;
        vec3 direction = normalize(position + vec3(0.0001));
        float pulse = sin(uTime * (1.3 + uEnergy * 2.0) + position.x * 2.1 + position.y * 2.7);
        vec3 animated = position + direction * pulse * (0.035 + uEnergy * 0.08);
        vec4 viewPosition = modelViewMatrix * vec4(animated, 1.0);
        gl_Position = projectionMatrix * viewPosition;
        gl_PointSize = min(48.0, aSize * (52.0 + uEnergy * 42.0) / max(1.0, -viewPosition.z));
        vGlow = 0.58 + 0.42 * pulse;
      }
    `,
    fragmentShader: `
      uniform vec3 uPrimary;
      uniform vec3 uSecondary;
      varying float vMix;
      varying float vGlow;
      void main() {
        float distanceFromCenter = length(gl_PointCoord - vec2(0.5));
        float halo = 1.0 - smoothstep(0.08, 0.5, distanceFromCenter);
        float core = 1.0 - smoothstep(0.0, 0.11, distanceFromCenter);
        vec3 color = mix(uPrimary, uSecondary, vMix);
        gl_FragColor = vec4(mix(color, vec3(1.0), core * 0.62), (halo * 0.65 + core * 0.35) * vGlow);
      }
    `,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  const linksMaterial = new THREE.LineBasicMaterial({
    color: STATES.idle.color,
    transparent: true,
    opacity: 0.16,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });

  function glowTexture() {
    const surface = document.createElement('canvas');
    surface.width = surface.height = 128;
    const context = surface.getContext('2d');
    const gradient = context.createRadialGradient(64, 64, 0, 64, 64, 64);
    gradient.addColorStop(0, 'rgba(255,255,255,1)');
    gradient.addColorStop(0.1, 'rgba(255,255,255,.85)');
    gradient.addColorStop(0.34, 'rgba(255,255,255,.22)');
    gradient.addColorStop(1, 'rgba(255,255,255,0)');
    context.fillStyle = gradient;
    context.fillRect(0, 0, 128, 128);
    return new THREE.CanvasTexture(surface);
  }
  const coreTexture = glowTexture();
  const coreMaterial = new THREE.SpriteMaterial({
    map: coreTexture,
    color: STATES.idle.color,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  const core = new THREE.Sprite(coreMaterial);
  core.scale.set(3.2, 3.2, 1);
  brain.add(core);

  const ringMaterial = new THREE.MeshBasicMaterial({
    color: STATES.idle.secondary,
    transparent: true,
    opacity: 0.27,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
  const ringGeometry = new THREE.TorusGeometry(2.55, 0.008, 3, 144);
  const rings = [0, 1, 2].map(index => {
    const ring = new THREE.Mesh(ringGeometry, ringMaterial);
    ring.rotation.set(index * 0.9 + 0.4, index * 0.7 + 0.2, index * 0.45);
    brain.add(ring);
    return ring;
  });

  let patternId = 'cortex';
  let points;
  let links;
  let signals;
  let edgePaths = [];
  let signalRecords = [];
  let signalPositions;

  function edgePoint(path, fraction, output) {
    const arc = Math.sin(Math.PI * fraction) * path.bend;
    output.x = path.a.x + (path.b.x - path.a.x) * fraction + path.normal.x * arc;
    output.y = path.a.y + (path.b.y - path.a.y) * fraction + path.normal.y * arc;
    output.z = path.a.z + (path.b.z - path.a.z) * fraction + path.normal.z * arc;
    return output;
  }

  function rebuild(count) {
    if (points) { brain.remove(points); points.geometry.dispose(); }
    if (links) { brain.remove(links); links.geometry.dispose(); }
    if (signals) { brain.remove(signals); signals.geometry.dispose(); }
    const network = buildPattern(patternId, count);
    const positions = new Float32Array(network.nodes.length * 3);
    const sizes = new Float32Array(network.nodes.length);
    const mixes = new Float32Array(network.nodes.length);
    network.nodes.forEach((node, index) => {
      positions.set([node.x, node.y, node.z], index * 3);
      sizes[index] = node.size;
      mixes[index] = node.mix;
    });
    const pointGeometry = new THREE.BufferGeometry();
    pointGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    pointGeometry.setAttribute('aSize', new THREE.BufferAttribute(sizes, 1));
    pointGeometry.setAttribute('aMix', new THREE.BufferAttribute(mixes, 1));
    points = new THREE.Points(pointGeometry, pointsMaterial);
    brain.add(points);

    edgePaths = network.edges.map(([from, to], index) => {
      const a = network.nodes[from], b = network.nodes[to];
      const midpoint = {x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, z: (a.z + b.z) / 2};
      const length = Math.hypot(midpoint.x, midpoint.y, midpoint.z) || 1;
      return {
        a, b,
        normal: {x: midpoint.x / length, y: midpoint.y / length, z: midpoint.z / length},
        bend: network.bend * (0.6 + (index % 7) * 0.13),
      };
    });
    const segments = 4;
    const linePositions = new Float32Array(edgePaths.length * segments * 6);
    const first = {x: 0, y: 0, z: 0};
    const second = {x: 0, y: 0, z: 0};
    let offset = 0;
    for (const path of edgePaths) {
      for (let segment = 0; segment < segments; segment += 1) {
        edgePoint(path, segment / segments, first);
        edgePoint(path, (segment + 1) / segments, second);
        linePositions.set([first.x, first.y, first.z, second.x, second.y, second.z], offset);
        offset += 6;
      }
    }
    const lineGeometry = new THREE.BufferGeometry();
    lineGeometry.setAttribute('position', new THREE.BufferAttribute(linePositions, 3));
    links = new THREE.LineSegments(lineGeometry, linksMaterial);
    brain.add(links);

    const signalCount = Math.min(140, Math.max(32, Math.round(network.nodes.length * 0.18)));
    signalPositions = new Float32Array(signalCount * 3);
    const signalSizes = new Float32Array(signalCount);
    const signalMixes = new Float32Array(signalCount);
    signalRecords = Array.from({length: signalCount}, (_, index) => {
      signalSizes[index] = 4.1 + (index % 4) * 0.55;
      signalMixes[index] = index % 3 === 0 ? 0 : 1;
      return {
        path: edgePaths[(index * 79 + index * index * 13) % edgePaths.length],
        phase: (index * 0.61803398875) % 1,
        speed: 0.18 + (index % 7) * 0.035,
      };
    });
    const signalGeometry = new THREE.BufferGeometry();
    signalGeometry.setAttribute('position', new THREE.BufferAttribute(signalPositions, 3));
    signalGeometry.setAttribute('aSize', new THREE.BufferAttribute(signalSizes, 1));
    signalGeometry.setAttribute('aMix', new THREE.BufferAttribute(signalMixes, 1));
    signals = new THREE.Points(signalGeometry, pointsMaterial);
    brain.add(signals);
    core.visible = network.core;
    rings.forEach(ring => {
      ring.visible = network.rings;
      ring.scale.setScalar(patternId === 'stream' ? 0.52 : 0.96);
    });
    countLabel.textContent = String(network.nodes.length);
    linkCountLabel.textContent = String(network.edges.length);
  }

  function setPattern(next) {
    if (!PATTERNS[next]) next = 'cortex';
    patternId = next;
    const position = PATTERN_IDS.indexOf(next) + 1;
    patternName.textContent = `${String(position).padStart(2, '0')} / ${PATTERNS[next].name}`;
    patternDescription.textContent = PATTERNS[next].description;
    for (const button of document.querySelectorAll('#patterns button')) {
      button.setAttribute('aria-pressed', String(button.dataset.pattern === next));
    }
    const url = new URL(window.location.href);
    url.searchParams.set('demo', next);
    window.history.replaceState(null, '', url);
    rebuild(Number(qualityInput.value));
  }

  let state = 'idle';
  let demo = false;
  let demoStarted = 0;
  let demoPatternStart = 0;
  let micStream = null;
  let micContext = null;
  let analyser = null;
  let micSamples = null;
  let dragging = false;
  let lastPointerX = 0;
  let lastPointerY = 0;
  let targetRotationX = 0.12;
  let targetRotationY = 0;
  let lastFrame = performance.now();
  let fpsFrames = 0;
  let fpsStarted = lastFrame;

  function setState(next) {
    state = next;
    stateLabel.textContent = STATES[next].label;
    for (const button of document.querySelectorAll('#states button')) {
      button.setAttribute('aria-pressed', String(button.dataset.state === next));
    }
  }
  function resize() {
    const bounds = stage.getBoundingClientRect();
    const pixelRatio = Math.min(1.75, window.devicePixelRatio || 1);
    const scale = Math.min(pixelRatio, Math.sqrt(2_000_000 / Math.max(1, bounds.width * bounds.height)));
    const width = Math.max(1, Math.round(bounds.width * scale));
    const height = Math.max(1, Math.round(bounds.height * scale));
    if (canvas.width !== width || canvas.height !== height) renderer.setSize(width, height, false);
    camera.aspect = bounds.width / Math.max(1, bounds.height);
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(stage);
  resize();
  const requestedDensity = new URLSearchParams(window.location.search).get('density');
  if (['160', '320', '640'].includes(requestedDensity)) qualityInput.value = requestedDensity;
  setPattern(new URLSearchParams(window.location.search).get('demo') || 'cortex');

  document.getElementById('patterns').addEventListener('click', event => {
    const button = event.target.closest('button[data-pattern]');
    if (!button) return;
    demo = false;
    cycleButton.setAttribute('aria-pressed', 'false');
    setPattern(button.dataset.pattern);
  });

  document.getElementById('states').addEventListener('click', event => {
    const button = event.target.closest('button[data-state]');
    if (!button) return;
    demo = false;
    cycleButton.setAttribute('aria-pressed', 'false');
    setState(button.dataset.state);
  });
  energyInput.addEventListener('input', () => {
    energyValue.textContent = `${energyInput.value}%`;
  });
  qualityInput.addEventListener('change', () => {
    const url = new URL(window.location.href);
    url.searchParams.set('density', qualityInput.value);
    window.history.replaceState(null, '', url);
    rebuild(Number(qualityInput.value));
  });
  cycleButton.addEventListener('click', () => {
    demo = !demo;
    if (demo) {
      demoStarted = performance.now();
      demoPatternStart = PATTERN_IDS.indexOf(patternId);
    }
    cycleButton.setAttribute('aria-pressed', String(demo));
  });

  async function stopMic() {
    micStream?.getTracks().forEach(track => track.stop());
    micStream = null;
    analyser = null;
    micSamples = null;
    if (micContext) await micContext.close().catch(() => {});
    micContext = null;
    micButton.setAttribute('aria-pressed', 'false');
    micButton.textContent = 'Use mic';
  }
  micButton.addEventListener('click', async () => {
    if (micStream) { await stopMic(); return; }
    try {
      micStream = await navigator.mediaDevices.getUserMedia({audio: true, video: false});
      micContext = new AudioContext();
      const source = micContext.createMediaStreamSource(micStream);
      analyser = micContext.createAnalyser();
      analyser.fftSize = 1024;
      source.connect(analyser);
      micSamples = new Float32Array(analyser.fftSize);
      micButton.setAttribute('aria-pressed', 'true');
      micButton.textContent = 'Stop mic';
      setState('listening');
    } catch (error) {
      await stopMic();
      showError(`Microphone unavailable: ${error.message}. Refresh to try again.`);
    }
  });
  window.addEventListener('pagehide', stopMic);

  canvas.addEventListener('pointerdown', event => {
    dragging = true;
    lastPointerX = event.clientX;
    lastPointerY = event.clientY;
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener('pointermove', event => {
    if (!dragging) return;
    targetRotationY += (event.clientX - lastPointerX) * 0.008;
    targetRotationX = Math.max(-1.2, Math.min(1.2, targetRotationX + (event.clientY - lastPointerY) * 0.008));
    lastPointerX = event.clientX;
    lastPointerY = event.clientY;
  });
  canvas.addEventListener('pointerup', () => { dragging = false; });
  canvas.addEventListener('pointercancel', () => { dragging = false; });
  canvas.addEventListener('wheel', event => {
    event.preventDefault();
    camera.position.z = Math.max(6.5, Math.min(20, camera.position.z + event.deltaY * 0.01));
  }, {passive: false});

  const primaryTarget = new THREE.Color();
  const secondaryTarget = new THREE.Color();
  const signalPosition = {x: 0, y: 0, z: 0};
  function animate(now) {
    requestAnimationFrame(animate);
    if (document.hidden) { lastFrame = now; fpsStarted = now; fpsFrames = 0; return; }
    const delta = Math.min(0.05, (now - lastFrame) / 1000);
    lastFrame = now;
    if (demo) {
      const demoIndex = Math.floor((now - demoStarted) / 6000);
      const demoPattern = PATTERN_IDS[(demoPatternStart + demoIndex) % PATTERN_IDS.length];
      if (demoPattern !== patternId) setPattern(demoPattern);
      const demoState = DEMO_STATES[demoIndex % DEMO_STATES.length];
      if (demoState !== state) setState(demoState);
    }
    let energy = Number(energyInput.value) / 100;
    if (analyser) {
      analyser.getFloatTimeDomainData(micSamples);
      let squareSum = 0;
      for (const sample of micSamples) squareSum += sample * sample;
      energy = Math.min(1, Math.sqrt(squareSum / micSamples.length) * 9);
      energyInput.value = String(Math.round(energy * 100));
      energyValue.textContent = `${energyInput.value}%`;
    }
    const settings = STATES[state];
    uniforms.uTime.value = now / 1000;
    uniforms.uEnergy.value += (energy - uniforms.uEnergy.value) * Math.min(1, delta * 6);
    const palette = PATTERNS[patternId].palette;
    primaryTarget.setHex(state === 'idle' ? palette[0] : settings.color);
    secondaryTarget.setHex(state === 'idle' ? palette[1] : settings.secondary);
    uniforms.uPrimary.value.lerp(primaryTarget, Math.min(1, delta * 4));
    uniforms.uSecondary.value.lerp(secondaryTarget, Math.min(1, delta * 4));
    linksMaterial.color.copy(uniforms.uPrimary.value);
    linksMaterial.opacity = 0.08 + energy * 0.15;
    coreMaterial.color.copy(uniforms.uPrimary.value);
    ringMaterial.color.copy(uniforms.uSecondary.value);
    core.scale.setScalar(2.7 + energy * 1.4 + Math.sin(now * 0.003) * 0.16);
    signalRecords.forEach((record, index) => {
      const progress = ((now / 1000) * record.speed * (0.6 + energy * 1.7)
        * (state === 'thinking' ? 1.55 : 1) + record.phase) % 1;
      edgePoint(record.path, progress, signalPosition);
      const offset = index * 3;
      signalPositions[offset] = signalPosition.x;
      signalPositions[offset + 1] = signalPosition.y;
      signalPositions[offset + 2] = signalPosition.z;
    });
    signals.geometry.attributes.position.needsUpdate = true;
    brain.rotation.y += (targetRotationY - brain.rotation.y) * Math.min(1, delta * 5);
    brain.rotation.x += (targetRotationX - brain.rotation.x) * Math.min(1, delta * 5);
    if (!dragging && !reducedMotion) {
      targetRotationY += delta * settings.speed * (0.5 + energy);
    }
    rings[0].rotation.z += delta * 0.11;
    rings[1].rotation.y -= delta * 0.09;
    rings[2].rotation.x += delta * 0.07;
    renderer.render(scene, camera);
    fpsFrames += 1;
    if (now - fpsStarted >= 500) {
      fpsLabel.textContent = String(Math.round(fpsFrames * 1000 / (now - fpsStarted)));
      callsLabel.textContent = String(renderer.info.render.calls);
      fpsStarted = now;
      fpsFrames = 0;
    }
  }
  requestAnimationFrame(animate);
}

start().catch(error => showError(`Visualizer failed: ${error.message}`));
