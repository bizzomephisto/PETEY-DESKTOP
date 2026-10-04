// Geometry-only generators for the five Three.js experiments. Coordinates are
// deterministic so switching density or comparing performance keeps each shape.
const TAU = Math.PI * 2;

function random(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let value = Math.imul(state ^ state >>> 15, 1 | state);
    value ^= value + Math.imul(value ^ value >>> 7, 61 | value);
    return ((value ^ value >>> 14) >>> 0) / 4294967296;
  };
}

function network(seed) {
  const nodes = [];
  const edges = [];
  const edgeKeys = new Set();
  const rng = random(seed);
  const node = (x, y, z, size = 2.4, mix = 0, group = 0) => {
    nodes.push({x, y, z, size, mix, group});
    return nodes.length - 1;
  };
  const edge = (a, b) => {
    if (a === b || a == null || b == null) return;
    const low = Math.min(a, b), high = Math.max(a, b);
    const key = low * 2048 + high;
    if (edgeKeys.has(key)) return;
    edgeKeys.add(key);
    edges.push([a, b]);
  };
  return {nodes, edges, rng, node, edge};
}

function nearest(net, candidates, distanceLimit, count = 2, sameGroup = false) {
  const limitSquared = distanceLimit * distanceLimit;
  for (const index of candidates) {
    const origin = net.nodes[index];
    const closest = [];
    for (const other of candidates) {
      if (other === index) continue;
      const target = net.nodes[other];
      if (sameGroup && origin.group !== target.group) continue;
      const dx = origin.x - target.x, dy = origin.y - target.y, dz = origin.z - target.z;
      const distance = dx * dx + dy * dy + dz * dz;
      if (distance > limitSquared) continue;
      if (closest.length < count || distance < closest[closest.length - 1].distance) {
        closest.push({other, distance});
        closest.sort((a, b) => a.distance - b.distance);
        if (closest.length > count) closest.pop();
      }
    }
    for (const item of closest) net.edge(index, item.other);
  }
}

function cortex(count) {
  const net = network(1125);
  for (let index = 0; index < count - 12; index += 1) {
    const side = index % 2 ? 1 : -1;
    const longitude = TAU * net.rng();
    const latitude = Math.acos(2 * net.rng() - 1);
    const depth = 0.38 + 0.62 * Math.cbrt(net.rng());
    const arc = Math.sin(latitude);
    net.node(
      side * (1.05 + Math.cos(longitude) * arc * depth * 0.92),
      Math.cos(latitude) * depth * 2.05,
      Math.sin(longitude) * arc * depth * 1.55,
      index % 29 === 0 ? 4.5 : 2.25 + (index % 5) * 0.23,
      side > 0 ? 1 : 0,
      side,
    );
  }
  nearest(net, net.nodes.map((_, index) => index), 0.86, 3, true);
  const bridge = [];
  for (let index = 0; index < 12; index += 1) {
    bridge.push(net.node(-0.85 + index * 1.7 / 11, Math.sin(index * 0.64) * 0.16, 0.04, 3.8, 0.5, 0));
    if (index) net.edge(bridge[index - 1], bridge[index]);
  }
  for (const side of [-1, 1]) {
    const terminal = side < 0 ? bridge[0] : bridge[bridge.length - 1];
    const peers = net.nodes.map((item, index) => ({item, index}))
      .filter(({item}) => item.group === side && Math.abs(item.y) < 0.8 && Math.abs(item.z) < 0.6)
      .sort((a, b) => Math.abs(a.item.x) - Math.abs(b.item.x)).slice(0, 6);
    for (const peer of peers) net.edge(terminal, peer.index);
  }
  return {...net, bend: 0.035, core: true, rings: false};
}

function lattice(count) {
  const net = network(2511);
  const columns = Math.max(8, Math.round(Math.sqrt(count * 1.45)));
  const rows = Math.ceil(count / columns);
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns && net.nodes.length < count; column += 1) {
      const x = (column / Math.max(1, columns - 1) - 0.5) * 7.0;
      const y = (row / Math.max(1, rows - 1) - 0.5) * 5.1;
      const ripple = Math.sin(x * 1.6 + y * 0.7) * 0.38 + Math.cos(y * 1.8 - x * 0.35) * 0.32;
      const index = net.node(x, y, ripple, (row + column) % 9 === 0 ? 3.9 : 2.1, (row + column) % 3 === 0 ? 1 : 0);
      if (column) net.edge(index - 1, index);
      if (row && index - columns >= 0) net.edge(index - columns, index);
      if (row && column && (row + column) % 2 === 0 && index - columns - 1 >= 0) net.edge(index - columns - 1, index);
    }
  }
  return {...net, bend: 0.012, core: false, rings: false};
}

function dendrites(count) {
  const net = network(4001);
  const root = net.node(0, 0, 0, 9, 1);
  const queue = [];
  for (let index = 0; index < 7; index += 1) {
    const angle = index / 7 * TAU;
    queue.push({parent: root, x: Math.cos(angle), y: Math.sin(angle), z: (index % 3 - 1) * 0.34, length: 0.9, depth: 0});
  }
  while (queue.length && net.nodes.length < count) {
    const branch = queue.shift();
    const parent = net.nodes[branch.parent];
    const scale = Math.hypot(branch.x, branch.y, branch.z) || 1;
    const x = parent.x + branch.x / scale * branch.length;
    const y = parent.y + branch.y / scale * branch.length;
    const z = parent.z + branch.z / scale * branch.length;
    const index = net.node(x, y, z, branch.depth < 2 ? 3.8 : 2.0 + net.rng() * 1.3, branch.depth % 3 === 0 ? 1 : 0);
    net.edge(branch.parent, index);
    if (branch.depth < 8) {
      for (const direction of [-1, 1]) {
        const twist = direction * (0.28 + net.rng() * 0.42);
        queue.push({
          parent: index,
          x: branch.x * Math.cos(twist) - branch.y * Math.sin(twist) + (net.rng() - 0.5) * 0.2,
          y: branch.x * Math.sin(twist) + branch.y * Math.cos(twist) + (net.rng() - 0.5) * 0.2,
          z: branch.z * 0.7 + (net.rng() - 0.5) * 0.6,
          length: branch.length * 0.8,
          depth: branch.depth + 1,
        });
      }
    }
  }
  return {...net, bend: 0.0, core: true, rings: false};
}

function constellation(count) {
  const net = network(5055);
  const hubs = [];
  for (let index = 0; index < 8; index += 1) {
    const angle = index / 8 * TAU;
    hubs.push(net.node(Math.cos(angle) * 2.45, Math.sin(angle) * 1.75, Math.sin(angle * 2.5) * 1.1, 7.2, 1, index));
    if (index) net.edge(hubs[index - 1], hubs[index]);
  }
  net.edge(hubs[7], hubs[0]);
  net.edge(hubs[0], hubs[4]);
  net.edge(hubs[2], hubs[6]);
  const groups = Array.from({length: 8}, () => []);
  for (let index = 8; index < count; index += 1) {
    const group = (index - 8) % 8;
    const hub = net.nodes[hubs[group]];
    const angle = TAU * net.rng();
    const radius = 0.22 + net.rng() * 0.9;
    const satellite = net.node(
      hub.x + Math.cos(angle) * radius,
      hub.y + Math.sin(angle) * radius * 0.8,
      hub.z + (net.rng() - 0.5) * 1.4,
      index % 17 === 0 ? 4.5 : 2.2,
      index % 4 === 0 ? 1 : 0,
      group,
    );
    groups[group].push(satellite);
    if (index % 3 === 0) net.edge(hubs[group], satellite);
  }
  for (const group of groups) nearest(net, group, 0.9, 2);
  return {...net, bend: 0.19, core: false, rings: true};
}

function axonStream(count) {
  const net = network(6901);
  const strands = 5;
  const steps = Math.ceil(count / strands);
  const grid = [];
  for (let step = 0; step < steps; step += 1) {
    grid[step] = [];
    for (let strand = 0; strand < strands && net.nodes.length < count; strand += 1) {
      const angle = step * 0.31 + strand / strands * TAU;
      const radius = 1.25 + 0.2 * Math.sin(step * 0.24 + strand);
      const index = net.node(
        Math.cos(angle) * radius,
        -3.15 + step / Math.max(1, steps - 1) * 6.3,
        Math.sin(angle) * radius,
        step % 13 === 0 ? 4.2 : 2.4,
        strand % 2,
        strand,
      );
      grid[step][strand] = index;
      if (step) net.edge(grid[step - 1][strand], index);
      if (step && step % 3 === 0 && strand) net.edge(grid[step - 1][strand - 1], index);
      if (step % 5 === 0 && strand) net.edge(grid[step][strand - 1], index);
    }
    if (step % 5 === 0 && grid[step].length === strands) net.edge(grid[step][0], grid[step][strands - 1]);
  }
  return {...net, bend: 0.055, core: false, rings: true};
}

export const PATTERNS = {
  cortex: {name: 'Cortex Mesh', description: 'Dual hemispheres and a glowing midline bridge', palette: [0x56b8ff, 0x9a78ff], make: cortex},
  lattice: {name: 'Synapse Field', description: 'A rippling sheet of densely linked processing cells', palette: [0x41e3d0, 0x68a8ff], make: lattice},
  dendrites: {name: 'Dendrite Grove', description: 'Branching neurons that fan out from a shared soma', palette: [0xffac52, 0xff78b7], make: dendrites},
  constellation: {name: 'Memory Constellation', description: 'Eight clusters exchanging signals across a hub network', palette: [0xb78bff, 0x67d8ff], make: constellation},
  stream: {name: 'Axon Stream', description: 'Intertwined signal fibers carrying pulses through space', palette: [0x37c7ff, 0xff6dbd], make: axonStream},
};

export function buildPattern(id, count) {
  const pattern = PATTERNS[id] || PATTERNS.cortex;
  return pattern.make(Math.max(80, Math.min(640, Math.round(count))));
}
