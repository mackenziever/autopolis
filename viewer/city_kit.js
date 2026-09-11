/**
 * Civitas City Kit — procedural daylight city + optional GLB citizens.
 * Buildings · roads · trees · low-poly citizens.
 *
 * HARD RULES (blob / "monster" prevention):
 * - loadCitizenGlb defaults to EMPTY pools (fail-closed)
 * - Known-bad assets (woman/xbot/cesium emissive monsters) are refused
 * - Skinned-mesh Box3 scale is clamped — never explode to building size
 * - GLB materials never get state-color flood / full-white emissive
 */
let _gltfLoader = null;
let _citizenTemplate = null;
const _citizenPool = [];
const _citizenPools = { male: [], female: [] };

/** One shared material for all window InstancedMesh across the whole city —
 * see buildFacadeWindows() for why (WebGL fragment-shader uniform limit). */
let _sharedWindowMat = null;
function sharedWindowMat(THREE) {
  if (!_sharedWindowMat) {
    // vertexColors:true is required for InstancedMesh.setColorAt() to actually
    // show up — instanceColor still gets computed into vColor without it, but
    // color_fragment only multiplies diffuseColor by vColor when USE_COLOR is
    // defined (from vertexColors), so every window rendered plain white
    // despite instanceColor holding the right per-window values (found live,
    // 2026-09-11, via renderer inspection: instanceColor array had varied
    // cyan/amber/dark entries, material.color was the only thing shown).
    _sharedWindowMat = new THREE.MeshBasicMaterial({ color: 0xffffff, vertexColors: true });
  }
  return _sharedWindowMat;
}

/** Filenames that historically produced the giant green bloom blob. */
const CITIZEN_GLB_BLOCKLIST = [
  /woman\.glb$/i,
  /xbot\.glb$/i,
  /cesium_man\.glb$/i,
  /flamingo/i,
  /robot/i,
];

function isBlockedCitizenGlb(url = '') {
  const u = String(url);
  // citizens/meshy/ is the vetted drop-in location documented in
  // viewer/assets/models/README.md — a file re-checked and placed there
  // (materials + scale verified, 2026-09-11) bypasses the name blocklist
  // below, which exists to catch the OLD known-bad files loaded from
  // citizens/ directly (still blocked, e.g. citizens/xbot.glb if it ever
  // reappears there).
  if (/citizens\/meshy\//i.test(u)) return false;
  return CITIZEN_GLB_BLOCKLIST.some((re) => re.test(u));
}

function sanitizeCitizenMaterials(root) {
  root.traverse((c) => {
    if (!c.isMesh) return;
    c.castShadow = true;
    c.receiveShadow = true;
    const mats = Array.isArray(c.material) ? c.material : c.material ? [c.material] : [];
    for (const m of mats) {
      if (m.emissive) {
        m.emissive.setRGB(0, 0, 0);
        m.emissiveIntensity = 0;
      }
      if (m.color) {
        const { r, g, b } = m.color;
        // Reject lime Mixamo / full-white chalk (reads as neon blob under bloom)
        if (g > 0.7 && g > r * 1.35 && g > b * 1.35 && !m.map) {
          m.color.setHex(0x64748b);
        } else if (r > 0.95 && g > 0.95 && b > 0.95 && !m.map) {
          m.color.setHex(0xc4b5a0);
        }
      }
      m.transparent = false;
      m.opacity = 1;
      m.depthWrite = true;
      m.needsUpdate = true;
    }
  });
}

function normalizeCitizenRoot(THREE, root, targetH = 1.05) {
  root.position.set(0, 0, 0);
  root.rotation.set(0, 0, 0);
  root.scale.set(1, 1, 1);
  // Cesium / some Meshy exports are Z-up
  const zUp = root.getObjectByName?.('Z_UP') || (root.children[0]?.name === 'Z_UP' ? root.children[0] : null);
  if (zUp || /z_?up/i.test(root.name || '')) {
    root.rotation.x = -Math.PI / 2;
  }
  // Skinned meshes need skeleton update before Box3 or size.y collapses → giant scale
  root.traverse((c) => {
    if (c.isSkinnedMesh) {
      c.skeleton?.update?.();
      c.computeBoundingBox?.();
      c.computeBoundingSphere?.();
    }
  });
  root.updateMatrixWorld(true);
  sanitizeCitizenMaterials(root);

  let box = new THREE.Box3().setFromObject(root);
  const size = new THREE.Vector3();
  box.getSize(size);
  const maxDim = Math.max(size.x, size.y, size.z, 0.01);
  // Clamp hard: citizens must stay human-scale, never building-scale "monsters"
  const raw = targetH / maxDim;
  const s = Math.min(3.0, Math.max(0.001, raw));
  if (raw > 3.0 || raw < 0.01) {
    console.warn('[city_kit] citizen scale clamped', { raw, s, size: size.toArray(), maxDim });
  }
  root.scale.setScalar(s);
  root.updateMatrixWorld(true);
  box = new THREE.Box3().setFromObject(root);
  const finalSize = new THREE.Vector3();
  box.getSize(finalSize);
  if (finalSize.y > 2.4) {
    root.scale.multiplyScalar(1.05 / finalSize.y);
    root.updateMatrixWorld(true);
    box = new THREE.Box3().setFromObject(root);
  }
  // Lift so soles sit on y=0 (fixes Meshy/Cesium centered pivots)
  root.position.y -= box.min.y;
  root.updateMatrixWorld(true);
  return root;
}

/** After final instance scale, snap feet to ground plane y=0 in parent space. */
export function groundCitizen(THREE, group) {
  if (!group) return;
  const prevY = group.position.y;
  group.position.y = 0;
  group.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(group);
  // Guard: bad bbox must not shove citizen into the sky / underground forever
  const dy = prevY - box.min.y;
  if (Number.isFinite(dy) && Math.abs(dy) < 50) {
    group.position.y = dy;
  } else {
    group.position.y = prevY;
  }
  group.updateMatrixWorld(true);
}

export function citizenPoolSize() {
  return {
    total: _citizenPool.length,
    male: _citizenPools.male.length,
    female: _citizenPools.female.length,
  };
}

export function clearCitizenPools() {
  _citizenPool.length = 0;
  _citizenPools.male = [];
  _citizenPools.female = [];
  _citizenTemplate = null;
}

const FEMALE_NAMES = new Set([
  'ada','cleo','elena','farah','hana','jade','lina','maria','sofia','giulia','anna','sara',
  'laura','chiara','martina','alice','emma','luna','nora','mia','iris','vera','rosa','nina',
]);
const MALE_NAMES = new Set([
  'bruno','diego','gio','ivan','kai','marco','luca','paolo','andrea','leo','nico','enzo',
  'alex','sam','max','tom','jack','ryan','omar','hugo','felix','carlo','dario','pietro',
]);

/** Infer gender from agent name / id. Stable and name-aware. */
export function inferCitizenGender(name = '', id = '') {
  const first = String(name || '').trim().split(/\s+/)[0].toLowerCase();
  if (FEMALE_NAMES.has(first)) return 'female';
  if (MALE_NAMES.has(first)) return 'male';
  // Italian -a endings often female (except Luca/Andrea handled above)
  if (/a$/.test(first) && first.length > 2) return 'female';
  if (/o$/.test(first) && first.length > 2) return 'male';
  const h = hashStr(String(id || name || 'x'));
  return h % 2 === 0 ? 'female' : 'male';
}

/**
 * Load citizen GLBs by gender.
 * FAIL-CLOSED: default is empty pools (no cesium_man surprise load).
 * urls: string[] | { male?: string[], female?: string[], all?: string[] }
 */
export async function loadCitizenGlb(THREE, GLTFLoader, urls = { male: [], female: [] }) {
  if (!_gltfLoader) _gltfLoader = new GLTFLoader();
  clearCitizenPools();

  let maleUrls = [];
  let femaleUrls = [];
  if (typeof urls === 'string') {
    maleUrls = [urls];
    femaleUrls = [urls];
  } else if (Array.isArray(urls)) {
    maleUrls = urls;
    femaleUrls = urls;
  } else if (urls && typeof urls === 'object') {
    maleUrls = urls.male || urls.all || [];
    femaleUrls = urls.female || urls.all || [];
  }

  async function loadOne(u, gender) {
    if (!u || isBlockedCitizenGlb(u)) {
      console.warn('[city_kit] GLB citizen BLOCKED', gender, u);
      return false;
    }
    try {
      const gltf = await _gltfLoader.loadAsync(u);
      const root = normalizeCitizenRoot(THREE, gltf.scene.clone(true), gender === 'female' ? 1.0 : 1.05);
      // Final reject if still oversized after normalize
      const box = new THREE.Box3().setFromObject(root);
      const size = new THREE.Vector3();
      box.getSize(size);
      if (size.y > 2.2 || size.x > 2.2 || size.z > 2.2) {
        console.warn('[city_kit] GLB citizen rejected oversized', u, size.toArray());
        return false;
      }
      root.userData.gender = gender;
      root.userData.sourceUrl = u;
      _citizenPools[gender].push(root);
      _citizenPool.push(root);
      if (!_citizenTemplate) _citizenTemplate = root;
      return true;
    } catch (e) {
      console.warn('[city_kit] GLB citizen skip', gender, u, e.message || e);
      return false;
    }
  }

  for (const u of maleUrls) await loadOne(u, 'male');
  for (const u of femaleUrls) await loadOne(u, 'female');
  // Cross-fill if one gender missing
  if (!_citizenPools.male.length && _citizenPools.female.length) {
    _citizenPools.male = _citizenPools.female.map((r) => r.clone(true));
  }
  if (!_citizenPools.female.length && _citizenPools.male.length) {
    _citizenPools.female = _citizenPools.male.map((r) => r.clone(true));
  }
  return _citizenPool.length > 0;
}

export function mulberry32(a) {
  return function () {
    let t = (a += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function hashStr(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

const THEMES = {
  daylight: {
    facades: [0xd4c4a8, 0xc9b8a0, 0xb8c4c8, 0xe8dcc8, 0xa8b0a0, 0xcfc8c0, 0xb0a090],
    roofs: [0x8b4513, 0x6b3a2a, 0x5c4033, 0x704214, 0x4a5560],
    asphalt: 0x3a3a3e,
    sidewalk: 0x9a958c,
    grass: 0x4a7c3f,
    park: 0x3d6b35,
    lane: 0xf5e6a3,
    winEmissive: 0xffe4a8,
    winColor: 0x87ceeb,
    winEmissiveIntensity: [0.35, 0.75],
    foliage: [0x3d8b37, 0x2e7d32, 0x558b2f, 0x1b5e20],
    trunk: 0x6b4423,
    strip: 0x5c4033,
    wallMetal: 0.02,
    wallRough: 0.85,
    wallEmissive: 0x000000,
    wallEmissiveIntensity: 0,
    wallOpacity: 1,
    wallTransparent: false,
  },
  cyberpunk: {
    // Massive Manas skyline reel (2026-09-11): saturated solid blocks (burgundy/
    // blue/violet/teal), not a single near-black tone — cyan window-dot bands read
    // as a lit night skyline against each hue instead of blending into a dark mass.
    facades: [0x7f1d1d, 0x1e3a8a, 0x4c1d95, 0x115e59, 0x9d174d, 0x1e293b, 0x581c87, 0x134e4a],
    roofs: [0x2e1065, 0x4c1d95, 0x1e1b4b, 0x3b0764, 0x334155, 0x7f1d1d],
    asphalt: 0x05060d,
    sidewalk: 0x0b0614,
    grass: 0x05060d,
    park: 0x0a1f1a,
    lane: 0x22d3ee,
    winEmissive: 0x22d3ee,
    winColor: 0x67e8f9,
    winEmissiveIntensity: [1.2, 2.0],
    foliage: [0x22d3ee, 0xe879f9, 0xa78bfa, 0xf472b6],
    trunk: 0x2e1065,
    strip: 0xe879f9,
    wallMetal: 0.35,
    wallRough: 0.55,
    wallEmissive: 0x0a0a12,
    wallEmissiveIntensity: 0.08,
    wallOpacity: 1,
    wallTransparent: false,
  },
};

function themeOf(name) {
  return THEMES[name] || THEMES.cyberpunk;
}

/** Low-poly / GLB citizen. opts: { gender:'male'|'female', variant:number } */
export function createCitizen(THREE, colorHex = 0x4a90d9, opts = {}) {
  const gender = opts.gender === 'female' || opts.gender === 'male'
    ? opts.gender
    : (opts.variant >= 0 ? (opts.variant % 2 === 0 ? 'female' : 'male') : 'male');
  const variant = opts.variant ?? -1;
  const pool = (_citizenPools[gender] && _citizenPools[gender].length)
    ? _citizenPools[gender]
    : (_citizenPool.length ? _citizenPool : (_citizenTemplate ? [_citizenTemplate] : []));

  const useGlb = opts.allowGlb === true && pool.length > 0;
  if (useGlb) {
    const idx = variant >= 0 ? variant % pool.length : Math.floor(Math.random() * pool.length);
    const g = pool[idx].clone(true);
    g.userData.kind = 'citizen';
    g.userData.fromGlb = true;
    g.userData.gender = gender;
    // Keep original GLB materials — never flood the body with state color
    g.userData.tintables = [];
    g.traverse((c) => {
      if (c.isMesh && c.material) {
        c.material = c.material.clone();
        if (c.material.emissive) {
          c.material.emissive.setRGB(0, 0, 0);
          c.material.emissiveIntensity = 0;
        }
      }
    });
    // No floating beacon sphere (bloom turns it into a blob)
    g.userData.beacon = null;
    return g;
  }

  // Procedural "peg-doll" citizen (Massive Manas skyline reel, 2026-09-11):
  // one neutral drop-shaped body + a single sphere head that carries the
  // state color — no separate arms/legs/hair. Reads clearly at city-wide
  // zoom (the previous capsule+limbs rig disappeared into noise at that scale).
  const g = new THREE.Group();
  const female = gender === 'female';
  const bodyMat = new THREE.MeshStandardMaterial({
    color: 0xd6cfc4,
    emissive: 0x1a1622,
    emissiveIntensity: 0.12,
    roughness: 0.6,
    metalness: 0.12,
  });
  const headMat = new THREE.MeshStandardMaterial({
    color: colorHex,
    emissive: colorHex,
    emissiveIntensity: 0.55,
    roughness: 0.35,
    metalness: 0.1,
  });

  const bodyR = female ? 0.16 : 0.18;
  const bodyH = female ? 0.5 : 0.56;
  const body = new THREE.Mesh(new THREE.ConeGeometry(bodyR, bodyH, 10, 1, true), bodyMat);
  body.position.y = bodyH / 2;
  body.castShadow = true;
  g.add(body);
  // Flat base so the cone doesn't taper to a point at ground level.
  const base = new THREE.Mesh(new THREE.CircleGeometry(bodyR, 10), bodyMat);
  base.rotation.x = Math.PI / 2;
  base.position.y = 0.01;
  g.add(base);

  const headR = female ? 0.155 : 0.165;
  const head = new THREE.Mesh(new THREE.SphereGeometry(headR, 14, 12), headMat);
  head.position.y = bodyH + headR * 0.9;
  head.castShadow = true;
  g.add(head);

  g.userData.tintables = [head];
  g.userData.body = body;
  g.userData.beacon = null;
  g.userData.kind = 'citizen';
  g.userData.gender = gender;
  return g;
}

export function tintCitizen(group, colorHex) {
  if (!group?.userData?.tintables) return;
  for (const m of group.userData.tintables) {
    if (!m.material?.color) continue;
    // Beacon only for GLB; soft accent for procedural body parts
    const isBeacon = m.name === 'beacon';
    if (group.userData.fromGlb && !isBeacon) continue;
    m.material.color.setHex(colorHex);
    if (m.material.emissive) {
      m.material.emissive.setHex(colorHex);
      m.material.emissiveIntensity = isBeacon ? 0.55 : 0.12;
    }
  }
}

/** Walk bob / face movement direction. */
export function animateCitizen(group, dt, moving) {
  // GLB: parent (live viewer) owns world Y / grounding — do not overwrite position.y here
  if (group?.userData?.fromGlb) return;
  const t = performance.now() * 0.008;
  if (group?.userData?.legs) {
    const amp = moving ? 0.35 : 0.05;
    group.userData.legs[0].rotation.x = Math.sin(t) * amp;
    group.userData.legs[1].rotation.x = Math.sin(t + Math.PI) * amp;
    return;
  }
  // Peg-doll body: no legs to swing — a small vertical bob reads as a footstep
  // bounce at city-wide zoom without needing a leg rig.
  const body = group?.userData?.body;
  if (body) {
    const amp = moving ? 0.045 : 0.012;
    body.position.y = (body.userData._baseY ??= body.position.y) + Math.abs(Math.sin(t * 1.6)) * amp;
  }
}

const ROOM_THEME_PALETTE = {
  cyberpunk: { floor: 0x0c0820, floorEm: 0x1e1b4b, ceil: 0x080612, ceilEm: 0x7c3aed, wall: 0x160b2e, lamp: 0xe879f9, fill: 0x22d3ee, accent: 0x4ade80 },
  warm: { floor: 0xc4b5a0, floorEm: 0x000000, ceil: 0xe8e0d0, ceilEm: 0x000000, wall: 0xd9cfc0, lamp: 0xfff2cc, fill: 0xffe8c8, accent: 0xfbbf24 },
  neon_garden: { floor: 0x0f2922, floorEm: 0x14532d, ceil: 0x052e16, ceilEm: 0x4ade80, wall: 0x14532d, lamp: 0x34d399, fill: 0x22d3ee, accent: 0xa3e635 },
  loft: { floor: 0x3f3f46, floorEm: 0x27272a, ceil: 0x52525b, ceilEm: 0x000000, wall: 0x71717a, lamp: 0xfbbf24, fill: 0xfde68a, accent: 0xfb923c },
  studio: { floor: 0xe7e5e4, floorEm: 0x000000, ceil: 0xfafaf9, ceilEm: 0x000000, wall: 0xd6d3d1, lamp: 0xfef3c7, fill: 0xffffff, accent: 0x94a3b8 },
};

/** Starter furniture by POI — sparse zones, open floor in the center (real rooms, not cubicles). */
function defaultRoomPropsForPoi(poiName = '') {
  const n = String(poiName).toLowerCase();
  if (/cafe|bar|lounge|noodle|stall|market/.test(n)) {
    return [
      { kind: 'counter', x: 0, z: -0.38, rot: 0 },
      { kind: 'neon_sign', x: 0, z: -0.44, rot: 0 },
      { kind: 'bar_stool', x: -0.22, z: -0.18, rot: 0.15 },
      { kind: 'bar_stool', x: 0.22, z: -0.18, rot: -0.15 },
      { kind: 'sofa', x: 0.36, z: 0.32, rot: -0.6 },
      { kind: 'table', x: 0.18, z: 0.28, rot: 0 },
      { kind: 'plant', x: -0.4, z: 0.38, rot: 0 },
    ];
  }
  if (/home|tower|residence/.test(n)) {
    // Bedroom corner | lounge | desk — walkable middle
    return [
      { kind: 'bed', x: 0.36, z: -0.34, rot: 0 },
      { kind: 'sofa', x: -0.34, z: 0.3, rot: 0.55 },
      { kind: 'table', x: -0.12, z: 0.28, rot: 0 },
      { kind: 'desk', x: -0.36, z: -0.34, rot: 0.1 },
      { kind: 'bookshelf', x: 0.44, z: 0.05, rot: -1.57 },
      { kind: 'poster', x: -0.44, z: 0, rot: 1.57 },
      { kind: 'plant', x: 0.4, z: 0.38, rot: 0 },
    ];
  }
  if (/office|lab|workshop|institute|library|maker|hub/.test(n)) {
    return [
      { kind: 'desk', x: -0.32, z: -0.32, rot: 0.2 },
      { kind: 'desk', x: 0.32, z: -0.28, rot: -0.25 },
      { kind: 'bookshelf', x: -0.42, z: 0.1, rot: 0.15 },
      { kind: 'bookshelf', x: 0.42, z: 0.15, rot: -0.15 },
      { kind: 'neon_sign', x: 0, z: -0.44, rot: 0 },
      { kind: 'plant', x: 0, z: 0.4, rot: 0 },
      { kind: 'bar_stool', x: -0.18, z: -0.08, rot: 0 },
    ];
  }
  if (/gym|arena|fitness/.test(n)) {
    return [
      { kind: 'counter', x: 0, z: -0.4, rot: 0 },
      { kind: 'neon_sign', x: 0, z: -0.44, rot: 0 },
      { kind: 'plant', x: -0.4, z: 0.36, rot: 0 },
      { kind: 'plant', x: 0.4, z: 0.36, rot: 0 },
      { kind: 'bar_stool', x: -0.28, z: 0.05, rot: 0 },
      { kind: 'bar_stool', x: 0.28, z: 0.05, rot: 0 },
    ];
  }
  // Default open loft
  return [
    { kind: 'sofa', x: -0.34, z: 0.3, rot: 0.45 },
    { kind: 'table', x: -0.1, z: 0.28, rot: 0 },
    { kind: 'desk', x: 0.34, z: -0.32, rot: -0.2 },
    { kind: 'plant', x: -0.4, z: -0.36, rot: 0 },
    { kind: 'plant', x: 0.4, z: 0.38, rot: 0 },
    { kind: 'neon_sign', x: 0, z: -0.42, rot: 0 },
    { kind: 'poster', x: 0.44, z: 0, rot: -1.57 },
  ];
}

function makeRoomProp(THREE, kind, themeKey = 'cyberpunk') {
  const neon = themeKey === 'cyberpunk' || themeKey === 'neon_garden';
  const wood = themeKey === 'warm' || themeKey === 'loft' ? 0x6b4423 : 0x312e81;
  const g = new THREE.Group();
  g.name = `prop_${kind}`;
  g.userData.propKind = kind;
  if (kind === 'sofa') {
    const base = new THREE.Mesh(
      new THREE.BoxGeometry(0.9, 0.28, 0.4),
      new THREE.MeshStandardMaterial({ color: neon ? 0x4c1d95 : 0x7c2d12, roughness: 0.7 })
    );
    base.position.y = 0.2;
    const back = new THREE.Mesh(
      new THREE.BoxGeometry(0.9, 0.35, 0.12),
      new THREE.MeshStandardMaterial({ color: neon ? 0x6d28d9 : 0x9a3412, roughness: 0.65 })
    );
    back.position.set(0, 0.42, -0.14);
    g.add(base, back);
  } else if (kind === 'plant') {
    const pot = new THREE.Mesh(
      new THREE.CylinderGeometry(0.08, 0.1, 0.14, 8),
      new THREE.MeshStandardMaterial({ color: 0x78716c, roughness: 0.8 })
    );
    pot.position.y = 0.07;
    const leaf = new THREE.Mesh(
      new THREE.SphereGeometry(0.16, 8, 8),
      new THREE.MeshStandardMaterial({
        color: 0x22c55e,
        emissive: neon ? 0x14532d : 0x000000,
        emissiveIntensity: neon ? 0.35 : 0,
        roughness: 0.6,
      })
    );
    leaf.position.y = 0.28;
    g.add(pot, leaf);
  } else if (kind === 'desk') {
    const desk = new THREE.Mesh(
      new THREE.BoxGeometry(0.85, 0.45, 0.4),
      new THREE.MeshStandardMaterial({ color: wood, roughness: 0.5, metalness: 0.25 })
    );
    desk.position.y = 0.25;
    desk.castShadow = true;
    const screen = new THREE.Mesh(
      new THREE.PlaneGeometry(0.55, 0.32),
      new THREE.MeshStandardMaterial({
        color: 0x22d3ee,
        emissive: 0x22d3ee,
        emissiveIntensity: 1.2,
        roughness: 0.2,
      })
    );
    screen.position.set(0, 0.72, 0.18);
    g.add(desk, screen);
  } else if (kind === 'neon_sign') {
    const sign = new THREE.Mesh(
      new THREE.PlaneGeometry(0.7, 0.28),
      new THREE.MeshStandardMaterial({
        color: 0xe879f9,
        emissive: 0xe879f9,
        emissiveIntensity: 1.6,
        roughness: 0.25,
      })
    );
    sign.position.y = 1.35;
    g.add(sign);
  } else if (kind === 'counter') {
    const c = new THREE.Mesh(
      new THREE.BoxGeometry(1.0, 0.7, 0.35),
      new THREE.MeshStandardMaterial({ color: neon ? 0x1e1b4b : 0x44403c, roughness: 0.45, metalness: 0.35 })
    );
    c.position.y = 0.35;
    g.add(c);
  } else if (kind === 'bed') {
    const mattress = new THREE.Mesh(
      new THREE.BoxGeometry(0.7, 0.22, 1.1),
      new THREE.MeshStandardMaterial({ color: neon ? 0x312e81 : 0xe7e5e4, roughness: 0.85 })
    );
    mattress.position.y = 0.2;
    const pillow = new THREE.Mesh(
      new THREE.BoxGeometry(0.5, 0.1, 0.25),
      new THREE.MeshStandardMaterial({ color: 0xfafafa, roughness: 0.9 })
    );
    pillow.position.set(0, 0.36, -0.35);
    g.add(mattress, pillow);
  } else if (kind === 'bookshelf') {
    const shelf = new THREE.Mesh(
      new THREE.BoxGeometry(0.45, 1.1, 0.22),
      new THREE.MeshStandardMaterial({ color: wood, roughness: 0.6 })
    );
    shelf.position.y = 0.55;
    g.add(shelf);
  } else if (kind === 'bar_stool') {
    const stool = new THREE.Mesh(
      new THREE.CylinderGeometry(0.14, 0.16, 0.42, 10),
      new THREE.MeshStandardMaterial({ color: neon ? 0x4c1d95 : 0x57534e, roughness: 0.45, metalness: 0.4 })
    );
    stool.position.y = 0.21;
    g.add(stool);
  } else if (kind === 'table') {
    const top = new THREE.Mesh(
      new THREE.CylinderGeometry(0.32, 0.32, 0.06, 16),
      new THREE.MeshStandardMaterial({ color: wood, roughness: 0.5 })
    );
    top.position.y = 0.42;
    const leg = new THREE.Mesh(
      new THREE.CylinderGeometry(0.05, 0.06, 0.4, 8),
      new THREE.MeshStandardMaterial({ color: 0x292524, roughness: 0.6 })
    );
    leg.position.y = 0.2;
    g.add(top, leg);
  } else if (kind === 'poster') {
    const poster = new THREE.Mesh(
      new THREE.PlaneGeometry(0.45, 0.6),
      new THREE.MeshStandardMaterial({
        color: neon ? 0x22d3ee : 0xf97316,
        emissive: neon ? 0x0e7490 : 0x000000,
        emissiveIntensity: neon ? 0.5 : 0,
        roughness: 0.7,
      })
    );
    poster.position.y = 1.15;
    g.add(poster);
  } else {
    const box = new THREE.Mesh(
      new THREE.BoxGeometry(0.3, 0.3, 0.3),
      new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.6 })
    );
    box.position.y = 0.15;
    g.add(box);
  }
  return g;
}

/**
 * Apply sim-managed room state (theme + props) — Massive Manas / Sims style.
 * roomState: { theme, props:[{kind,x,z,rot}], layout_version }
 */
export function applyRoomLayout(THREE, building, roomState) {
  if (!building?.userData?.interior || !roomState) return false;
  const themeKey = roomState.theme || 'cyberpunk';
  const pal = ROOM_THEME_PALETTE[themeKey] || ROOM_THEME_PALETTE.cyberpunk;
  const dims = building.userData.dims || {};
  const iw = dims.iw || 1.8;
  const id_ = dims.id || 1.8;

  const floor = building.userData.floor;
  if (floor?.material) {
    floor.material.color.setHex(pal.floor);
    if (floor.material.emissive) floor.material.emissive.setHex(pal.floorEm);
    floor.material.emissiveIntensity = pal.floorEm ? 0.25 : 0;
  }
  const ceil = building.userData.ceil;
  if (ceil?.material) {
    ceil.material.color.setHex(pal.ceil);
    if (ceil.material.emissive) ceil.material.emissive.setHex(pal.ceilEm);
    ceil.material.emissiveIntensity = pal.ceilEm ? 0.15 : 0;
  }
  const shell = building.userData.shell;
  if (shell?.material) shell.material.color.setHex(pal.wall);
  const lamp = building.userData.roomLamp;
  if (lamp) lamp.color.setHex(pal.lamp);
  const fill = building.userData.roomFill;
  if (fill && pal.fill) fill.color.setHex(pal.fill);
  const accent = building.userData.roomAccent;
  if (accent && pal.accent) accent.color.setHex(pal.accent);
  const neonRoom = themeKey === 'cyberpunk' || themeKey === 'neon_garden';
  if (floor?.material) floor.material.emissiveIntensity = neonRoom ? 0.32 : pal.floorEm ? 0.08 : 0;
  if (ceil?.material) ceil.material.emissiveIntensity = neonRoom ? 0.22 : pal.ceilEm ? 0.06 : 0;
  const trim = building.userData.trim;
  if (trim?.material) {
    const tc = neonRoom ? 0x22d3ee : 0xfbbf24;
    trim.material.color.setHex(tc);
    if (trim.material.emissive) trim.material.emissive.setHex(tc);
  }
  const floorGrid = building.userData.floorGrid;
  if (floorGrid?.material) {
    const mats = Array.isArray(floorGrid.material) ? floorGrid.material : [floorGrid.material];
    mats.forEach((m, i) => {
      m.transparent = true;
      m.opacity = neonRoom ? 0.55 : 0.22;
      if (m.color) m.color.setHex(i === 0 ? (neonRoom ? 0x22d3ee : 0x94a3b8) : neonRoom ? 0x4c1d95 : 0xcbd5e1);
    });
  }

  let furniture = building.userData.furniture;
  if (!furniture) {
    furniture = new THREE.Group();
    furniture.name = 'furniture';
    building.userData.interior.add(furniture);
    building.userData.furniture = furniture;
  }
  while (furniture.children.length) {
    const ch = furniture.children[0];
    furniture.remove(ch);
    ch.traverse?.((o) => {
      if (o.geometry) o.geometry.dispose?.();
      if (o.material) {
        if (Array.isArray(o.material)) o.material.forEach((m) => m.dispose?.());
        else o.material.dispose?.();
      }
    });
  }

  for (const p of roomState.props || []) {
    const mesh = makeRoomProp(THREE, p.kind || 'plant', themeKey);
    const nx = Number(p.x) || 0;
    const nz = Number(p.z) || 0;
    // Spread toward walls; leave open walkable floor in the middle
    mesh.position.set(nx * iw * 0.92, 0, nz * id_ * 0.92);
    mesh.rotation.y = Number(p.rot) || 0;
    // Human-scale furniture — do NOT grow with room (that filled lofts into clutter)
    const propScale = Math.min(1.2, Math.max(0.95, 5.5 / Math.max(6, Math.min(iw, id_))));
    mesh.scale.setScalar(propScale);
    furniture.add(mesh);
  }

  building.userData.roomTheme = themeKey;
  building.userData.layoutVersion = Number(roomState.layout_version) || 0;
  return true;
}

/**
 * Building shell + enterable interior.
 * Exterior: solid dark prism + cyan window bands (final Civitas look).
 * Interior loft stays hidden until entered.
 */
export function createBuilding(THREE, opts = {}) {
  const {
    w = 5.5,
    h = 4,
    d = 5.5,
    seed = 1,
    theme = 'cyberpunk',
    facade = null,
    interactiveMeta = null,
    enterable = true,
  } = opts;
  const T = themeOf(theme);
  // POI accent colors stay as neon trim — body always dark charcoal (screenshot final)
  const accentCol = facade ?? T.strip;
  const bodyCol =
    theme === 'cyberpunk'
      ? T.facades[seed % T.facades.length]
      : facade ?? T.facades[seed % T.facades.length];
  const rnd = mulberry32(seed);
  const g = new THREE.Group();
  const exterior = new THREE.Group();
  const interior = new THREE.Group();
  exterior.name = 'exterior';
  interior.name = 'interior';
  interior.visible = false;
  g.add(exterior);
  g.add(interior);
  let doorHit = null;

  const thick = Math.min(0.18, Math.min(w, d) * 0.03);
  const doorW = Math.min(2.0, Math.max(1.2, w * 0.26));
  const doorH = Math.min(2.4, Math.max(1.9, h * 0.42));

  // Unlit materials — MeshStandard vanished into the void under bloom
  const bodyMat = new THREE.MeshBasicMaterial({ color: bodyCol });
  const body = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), bodyMat);
  body.position.y = h / 2;
  body.castShadow = true;
  body.receiveShadow = true;
  if (interactiveMeta) body.userData.poi = interactiveMeta;
  body.userData.buildingRoot = g;
  exterior.add(body);

  // Magenta neon mid-belt
  if (theme === 'cyberpunk') {
    const strip = new THREE.Mesh(
      new THREE.BoxGeometry(w + 0.05, 0.1, d + 0.05),
      new THREE.MeshBasicMaterial({ color: T.strip })
    );
    strip.position.y = Math.min(h * 0.18, 0.95);
    exterior.add(strip);
  }

  // Door glow + hit (carved look without hollow shell)
  if (enterable) {
    const frame = new THREE.Mesh(
      new THREE.BoxGeometry(doorW + 0.06, doorH + 0.06, 0.05),
      new THREE.MeshStandardMaterial({
        color: T.strip,
        emissive: theme === 'cyberpunk' ? T.strip : 0x334455,
        emissiveIntensity: theme === 'cyberpunk' ? 1.0 : 0.2,
        roughness: 0.35,
      })
    );
    frame.position.set(0, doorH / 2, d / 2 + 0.02);
    exterior.add(frame);
    const doorPanel = new THREE.Mesh(
      new THREE.BoxGeometry(doorW * 0.92, doorH * 0.92, 0.04),
      new THREE.MeshStandardMaterial({
        color: 0x0a0a12,
        emissive: 0x1e1b4b,
        emissiveIntensity: 0.35,
        roughness: 0.6,
      })
    );
    doorPanel.position.set(0, doorH / 2, d / 2 + 0.035);
    exterior.add(doorPanel);
    doorHit = new THREE.Mesh(
      new THREE.PlaneGeometry(doorW, doorH),
      new THREE.MeshBasicMaterial({ visible: false, side: THREE.DoubleSide })
    );
    doorHit.position.set(0, doorH / 2, d / 2 + 0.05);
    doorHit.userData.poi = interactiveMeta;
    doorHit.userData.buildingRoot = g;
    doorHit.userData.isDoor = true;
    exterior.add(doorHit);
    g.userData.doorHit = doorHit;
  }

  // Window grid (Massive Manas skyline reel, 2026-09-11): a dense 2D grid of
  // individually-lit windows per facade — NOT a few continuous horizontal
  // bands. Mixed cyan/amber "on" state with some windows dark reproduces the
  // punctuated night-skyline look (previous bands read as flat stripes).
  const onColors = [T.winEmissive || 0x22d3ee, 0xfbbf24, 0x67e8f9];
  const offCol = new THREE.Color(bodyCol).multiplyScalar(0.5);
  const winW = Math.min(0.42, Math.max(0.2, w / 11));
  const winH = Math.min(0.3, Math.max(0.16, h / 15));
  const cols = Math.max(3, Math.round((w * 0.82) / (winW * 1.7)));
  const winRows = Math.max(4, Math.round((h * 0.74) / (winH * 1.9)));
  const yTop = h * 0.92;
  const yBottom = Math.max(doorH + 0.3, h * 0.14);
  const winGeo = new THREE.BoxGeometry(winW, winH, 0.06);
  const dummy = new THREE.Object3D();
  const tmpCol = new THREE.Color();

  function buildFacadeWindows(faceSpan, place) {
    const count = cols * winRows;
    // One shared material for every window InstancedMesh in the whole city:
    // a fresh MeshBasicMaterial per facade x per building (hundreds of
    // buildings) blew past MAX_FRAGMENT_UNIFORM_VECTORS(1024) — WebGL then
    // fails shader compilation and falls back to solid white for the mesh.
    // Per-instance color (setColorAt below) still varies freely with one
    // shared material; only the compiled program is shared.
    const inst = new THREE.InstancedMesh(winGeo, sharedWindowMat(THREE), count);
    let idx = 0;
    for (let ry = 0; ry < winRows; ry++) {
      const py = yBottom + (ry / Math.max(1, winRows - 1)) * (yTop - yBottom);
      for (let cx = 0; cx < cols; cx++) {
        const along = (cx / Math.max(1, cols - 1) - 0.5) * (faceSpan * 0.82);
        const skipForDoor = place.isFront && enterable && py < doorH + 0.24 && Math.abs(along) < doorW / 2 + 0.15;
        if (skipForDoor) {
          dummy.scale.set(0, 0, 0);
        } else {
          dummy.position.copy(place.pos(along, py));
          dummy.rotation.set(0, place.rotY, 0);
          dummy.scale.set(1, 1, 1);
        }
        dummy.updateMatrix();
        inst.setMatrixAt(idx, dummy.matrix);
        const lit = rnd() < 0.62;
        tmpCol.set(lit ? onColors[Math.floor(rnd() * onColors.length)] : offCol);
        inst.setColorAt(idx, tmpCol);
        idx++;
      }
    }
    inst.instanceMatrix.needsUpdate = true;
    if (inst.instanceColor) inst.instanceColor.needsUpdate = true;
    exterior.add(inst);
    return inst;
  }

  // Kept for setBuildingOccupancy(): lit-per-citizen overrides pick a single
  // consistent "occupied" color instead of the randomized on/off mix above.
  const windowInstances = [
    buildFacadeWindows(w, { isFront: true, rotY: 0, pos: (along, py) => new THREE.Vector3(along, py, d / 2 + 0.035) }),
    buildFacadeWindows(w, { isFront: false, rotY: Math.PI, pos: (along, py) => new THREE.Vector3(-along, py, -d / 2 - 0.035) }),
    buildFacadeWindows(d, { isFront: false, rotY: Math.PI / 2, pos: (along, py) => new THREE.Vector3(w / 2 + 0.035, py, along) }),
    buildFacadeWindows(d, { isFront: false, rotY: -Math.PI / 2, pos: (along, py) => new THREE.Vector3(-w / 2 - 0.035, py, -along) }),
  ];
  g.userData.windowInstances = windowInstances;
  g.userData.windowOnColor = new THREE.Color(T.winEmissive || 0x22d3ee);
  g.userData.windowOffColor = offCol;
  g.userData.windowOccupancy = -1;

  const roofH = 0.28 + rnd() * 0.35;
  const roof = new THREE.Mesh(
    new THREE.BoxGeometry(w + 0.14, roofH, d + 0.14),
    new THREE.MeshBasicMaterial({ color: T.roofs[seed % T.roofs.length] })
  );
  roof.position.y = h + roofH / 2;
  roof.castShadow = true;
  exterior.add(roof);

  // —— Interior loft (hidden until enter) ——
  const expand = enterable ? 1.85 : 1.0;
  const iw = Math.max(w - thick * 2, Math.min(w, d) * 0.92) * expand;
  const id_ = Math.max(d - thick * 2, Math.min(w, d) * 0.92) * expand;
  const roomH = enterable
    ? Math.max(5.2, Math.min(7.2, Math.max(h * 1.15, Math.min(w, d) * expand * 0.42)))
    : Math.min(h - 0.15, Math.max(2.8, Math.min(w, d) * 0.55));
  const pal = ROOM_THEME_PALETTE[theme] || ROOM_THEME_PALETTE.cyberpunk;
  const neonRoom = theme === 'cyberpunk' || theme === 'neon_garden';

  const floor = new THREE.Mesh(
    new THREE.BoxGeometry(iw, 0.07, id_),
    new THREE.MeshStandardMaterial({
      color: pal.floor,
      roughness: 0.78,
      metalness: neonRoom ? 0.28 : 0.12,
      emissive: pal.floorEm,
      emissiveIntensity: neonRoom ? 0.32 : 0.05,
    })
  );
  floor.position.y = 0.035;
  floor.receiveShadow = true;
  floor.name = 'floor';
  floor.userData.structure = true;
  interior.add(floor);

  // Floor neon grid (visible when entered — Manas loft cue)
  const floorGrid = new THREE.GridHelper(
    Math.min(iw, id_) * 0.92,
    Math.max(6, Math.floor(Math.min(iw, id_) * 2.2)),
    neonRoom ? 0x22d3ee : 0x94a3b8,
    neonRoom ? 0x4c1d95 : 0xcbd5e1
  );
  floorGrid.position.y = 0.08;
  {
    const mats = Array.isArray(floorGrid.material) ? floorGrid.material : [floorGrid.material];
    mats.forEach((m) => {
      m.transparent = true;
      m.opacity = neonRoom ? 0.55 : 0.25;
    });
  }
  floorGrid.name = 'floorGrid';
  floorGrid.userData.structure = true;
  floorGrid.visible = false;
  interior.add(floorGrid);

  const ceil = new THREE.Mesh(
    new THREE.BoxGeometry(iw, 0.06, id_),
    new THREE.MeshStandardMaterial({
      color: pal.ceil,
      roughness: 0.88,
      emissive: pal.ceilEm,
      emissiveIntensity: neonRoom ? 0.22 : 0.04,
    })
  );
  ceil.position.y = roomH;
  ceil.name = 'ceil';
  ceil.userData.structure = true;
  interior.add(ceil);

  // Feature wall strip (back wall neon trim)
  const trim = new THREE.Mesh(
    new THREE.BoxGeometry(iw * 0.92, 0.06, 0.04),
    new THREE.MeshStandardMaterial({
      color: neonRoom ? 0x22d3ee : 0xfbbf24,
      emissive: neonRoom ? 0x22d3ee : 0xf59e0b,
      emissiveIntensity: 0.85,
      roughness: 0.25,
      metalness: 0.4,
    })
  );
  trim.position.set(0, roomH * 0.42, -id_ / 2 + 0.08);
  trim.name = 'trim';
  trim.userData.structure = true;
  interior.add(trim);

  const innerMat = new THREE.MeshStandardMaterial({
    color: pal.wall,
    roughness: 0.78,
    metalness: neonRoom ? 0.12 : 0.04,
    side: THREE.BackSide,
    emissive: neonRoom ? 0x1e1b4b : 0x000000,
    emissiveIntensity: neonRoom ? 0.12 : 0,
  });
  const shell = new THREE.Mesh(new THREE.BoxGeometry(iw, roomH, id_), innerMat);
  shell.position.y = roomH / 2;
  shell.name = 'shell';
  shell.userData.structure = true;
  interior.add(shell);

  // Corner pillars + rug — loft, not empty box
  const pillarMat = new THREE.MeshStandardMaterial({
    color: neonRoom ? 0x312e81 : 0xa8a29e,
    emissive: neonRoom ? 0x22d3ee : 0x000000,
    emissiveIntensity: neonRoom ? 0.35 : 0,
    metalness: 0.4,
    roughness: 0.35,
  });
  const pillarInsetX = iw * 0.42;
  const pillarInsetZ = id_ * 0.42;
  for (const [px, pz] of [
    [-pillarInsetX, -pillarInsetZ],
    [pillarInsetX, -pillarInsetZ],
    [-pillarInsetX, pillarInsetZ],
    [pillarInsetX, pillarInsetZ],
  ]) {
    const pillar = new THREE.Mesh(new THREE.BoxGeometry(0.12, roomH * 0.92, 0.12), pillarMat);
    pillar.position.set(px, roomH * 0.46, pz);
    pillar.userData.structure = true;
    interior.add(pillar);
  }
  const rug = new THREE.Mesh(
    new THREE.BoxGeometry(iw * 0.55, 0.025, id_ * 0.45),
    new THREE.MeshStandardMaterial({
      color: neonRoom ? 0x4c1d95 : 0xb45309,
      emissive: neonRoom ? 0x2e1065 : 0x000000,
      emissiveIntensity: neonRoom ? 0.25 : 0,
      roughness: 0.9,
    })
  );
  rug.position.set(0, 0.08, 0.05);
  rug.userData.structure = true;
  interior.add(rug);
  if (neonRoom) {
    for (const side of [-1, 1]) {
      const panel = new THREE.Mesh(
        new THREE.BoxGeometry(0.04, roomH * 0.55, id_ * 0.35),
        new THREE.MeshStandardMaterial({
          color: side < 0 ? 0xe879f9 : 0x22d3ee,
          emissive: side < 0 ? 0xe879f9 : 0x22d3ee,
          emissiveIntensity: 0.55,
          roughness: 0.3,
          metalness: 0.45,
        })
      );
      panel.position.set(side * (iw / 2 - 0.1), roomH * 0.45, 0);
      panel.userData.structure = true;
      interior.add(panel);
    }
  }

  const furniture = new THREE.Group();
  furniture.name = 'furniture';
  interior.add(furniture);

  // Multi-light loft (key + fill + accent, Manas interior glow): created
  // LAZILY on first enter (ensureRoomLights below), not here. With ~100+
  // enterable buildings, 3 real PointLight each — even invisible — pushed
  // WebGL's fragment shader past MAX_FRAGMENT_UNIFORM_VECTORS(1024): the
  // preprocessor sizes light-uniform arrays from every light PRESENT in the
  // scene, not just the currently-visible ones (found live, 2026-09-11: 381
  // PointLight for ~127 enterable buildings, every affected mesh rendered
  // solid white). Only the single currently-entered building ever needs
  // these three lights to exist.
  g.userData.kind = 'building';
  g.userData.enterable = !!enterable;
  g.userData.dims = { w, h, d, doorW, doorH, iw, id: id_, roomH };
  g.userData.exterior = exterior;
  g.userData.interior = interior;
  g.userData.furniture = furniture;
  g.userData.floor = floor;
  g.userData.ceil = ceil;
  g.userData.shell = shell;
  g.userData.roomLamp = null;
  g.userData.roomFill = null;
  g.userData.roomAccent = null;
  g.userData.floorGrid = floorGrid;
  g.userData.trim = trim;
  g.userData.roomTheme = theme;
  g.userData.layoutVersion = 0;
  g.userData.poi = interactiveMeta;
  g.userData.hitMesh = doorHit || exterior.children[0];
  g.userData.entered = false;
  g.userData.selected = false;

  const poiLabel = (interactiveMeta && interactiveMeta.name) || '';
  applyRoomLayout(THREE, g, {
    theme,
    props: defaultRoomPropsForPoi(poiLabel),
    layout_version: 0,
  });

  // Large invisible pick volume — easy click from aerial camera
  const pick = new THREE.Mesh(
    new THREE.BoxGeometry(w * 1.15, h + 0.6, d * 1.15),
    new THREE.MeshBasicMaterial({ visible: false, side: THREE.DoubleSide })
  );
  pick.position.y = (h + 0.6) / 2;
  pick.userData.buildingRoot = g;
  pick.userData.isPickVolume = true;
  g.add(pick);
  g.userData.pickVolume = pick;

  // Selection halo (ring at base)
  const halo = new THREE.Mesh(
    new THREE.RingGeometry(Math.max(w, d) * 0.55, Math.max(w, d) * 0.72, 32),
    new THREE.MeshBasicMaterial({
      color: 0x22d3ee,
      transparent: true,
      opacity: 0.85,
      side: THREE.DoubleSide,
      depthWrite: false,
    })
  );
  halo.rotation.x = -Math.PI / 2;
  halo.position.y = 0.08;
  halo.visible = false;
  g.add(halo);
  g.userData.selectHalo = halo;

  return g;
}

/** Scaffold / funding site — visible between propose and city_build complete. */
export function createConstructionSite(THREE, opts = {}) {
  const w = opts.w ?? 2.2;
  const h = opts.h ?? 1.4;
  const d = opts.d ?? 2.2;
  const status = opts.status || 'funding';
  const theme = opts.theme || 'cyberpunk';
  const g = new THREE.Group();

  const baseCol = status === 'building' ? 0xfb923c : 0xfbbf24;
  const pad = new THREE.Mesh(
    new THREE.BoxGeometry(w * 1.05, 0.12, d * 1.05),
    new THREE.MeshStandardMaterial({
      color: 0x1e293b,
      emissive: baseCol,
      emissiveIntensity: 0.25,
      roughness: 0.8,
      metalness: 0.2,
    })
  );
  pad.position.y = 0.06;
  g.add(pad);

  // Scaffold frame
  const beamMat = new THREE.MeshStandardMaterial({
    color: baseCol,
    emissive: baseCol,
    emissiveIntensity: status === 'building' ? 0.55 : 0.3,
    roughness: 0.45,
    metalness: 0.55,
    transparent: true,
    opacity: 0.9,
  });
  const posts = [
    [-w * 0.42, -d * 0.42],
    [w * 0.42, -d * 0.42],
    [-w * 0.42, d * 0.42],
    [w * 0.42, d * 0.42],
  ];
  for (const [px, pz] of posts) {
    const post = new THREE.Mesh(new THREE.BoxGeometry(0.1, h, 0.1), beamMat);
    post.position.set(px, h / 2, pz);
    g.add(post);
  }
  const top = new THREE.Mesh(new THREE.BoxGeometry(w * 0.9, 0.08, d * 0.9), beamMat);
  top.position.y = h;
  g.add(top);

  // Crane tint for building phase
  if (status === 'building') {
    const boom = new THREE.Mesh(
      new THREE.BoxGeometry(0.08, 0.08, d * 1.4),
      new THREE.MeshStandardMaterial({
        color: 0xe879f9,
        emissive: 0xe879f9,
        emissiveIntensity: 0.7,
        metalness: 0.6,
      })
    );
    boom.position.set(0, h + 0.6, 0);
    g.add(boom);
    const mast = new THREE.Mesh(
      new THREE.CylinderGeometry(0.06, 0.08, h + 0.8, 6),
      beamMat
    );
    mast.position.set(w * 0.35, (h + 0.8) / 2, -d * 0.35);
    g.add(mast);
  }

  const ring = new THREE.Mesh(
    new THREE.RingGeometry(Math.max(w, d) * 0.55, Math.max(w, d) * 0.75, 28),
    new THREE.MeshBasicMaterial({
      color: baseCol,
      transparent: true,
      opacity: 0.75,
      side: THREE.DoubleSide,
      depthWrite: false,
    })
  );
  ring.rotation.x = -Math.PI / 2;
  ring.position.y = 0.1;
  g.add(ring);

  g.userData.kind = 'construction_site';
  g.userData.enterable = false;
  g.userData.status = status;
  g.userData.poi = opts.meta || null;
  g.userData.projectId = opts.projectId || '';
  g.userData.pulse = ring;
  g.userData.beamMat = beamMat;
  g.userData.theme = theme;
  return g;
}

export function updateConstructionSiteStatus(site, status) {
  if (!site?.userData || site.userData.kind !== 'construction_site') return;
  site.userData.status = status;
  const col = status === 'building' ? 0xfb923c : 0xfbbf24;
  if (site.userData.pulse?.material) site.userData.pulse.material.color.setHex(col);
  if (site.userData.beamMat) {
    site.userData.beamMat.color.setHex(col);
    site.userData.beamMat.emissive?.setHex(col);
    site.userData.beamMat.emissiveIntensity = status === 'building' ? 0.55 : 0.3;
  }
}

/** Highlight building as selected (halo only — never mutate shared materials). */
export function setBuildingSelected(building, selected) {
  if (!building?.userData) return;
  building.userData.selected = !!selected;
  if (building.userData.selectHalo) {
    building.userData.selectHalo.visible = !!selected && !building.userData.entered;
  }
}

/** Light up exactly `count` windows (one per citizen currently inside),
 * leaving the rest dark — on top of the base random on/off skyline pattern
 * baked in at createBuilding() time. No-op if count hasn't changed since the
 * last call (cheap to call every WS tick for every building). */
export function setBuildingOccupancy(building, count) {
  const insts = building?.userData?.windowInstances;
  if (!insts || !insts.length) return;
  const n = Math.max(0, Math.round(count) || 0);
  if (building.userData.windowOccupancy === n) return;
  building.userData.windowOccupancy = n;
  const onCol = building.userData.windowOnColor;
  const offCol = building.userData.windowOffColor;
  let remaining = n;
  for (const inst of insts) {
    for (let i = 0; i < inst.count; i++) {
      inst.setColorAt(i, remaining > 0 ? onCol : offCol);
      if (remaining > 0) remaining--;
    }
    if (inst.instanceColor) inst.instanceColor.needsUpdate = true;
  }
}

/** Create this building's 3 interior PointLight on first enter (see
 * createBuilding() for why they're lazy, not always-present). Re-applies the
 * building's current room theme colors — same palette applyRoomLayout() uses. */
function ensureRoomLights(THREE, building) {
  if (building.userData.roomLamp) return;
  const { w, d, iw, id: id_, roomH } = building.userData.dims || {};
  const theme = building.userData.roomTheme || 'cyberpunk';
  const pal = ROOM_THEME_PALETTE[theme] || ROOM_THEME_PALETTE.cyberpunk;
  const neonRoom = theme === 'cyberpunk' || theme === 'neon_garden';
  const interior = building.userData.interior;
  if (!interior) return;

  const lamp = new THREE.PointLight(pal.lamp, neonRoom ? 0.85 : 0.6, Math.max(w, d) * 3.0, 1.15);
  lamp.position.set(0, roomH * 0.82, 0);
  lamp.name = 'roomLamp';
  lamp.userData.structure = true;
  interior.add(lamp);

  const roomFill = new THREE.PointLight(pal.fill || 0x22d3ee, neonRoom ? 0.42 : 0.22, Math.max(w, d) * 2.6, 1.4);
  roomFill.position.set(-iw * 0.28, roomH * 0.55, id_ * 0.22);
  roomFill.name = 'roomFill';
  roomFill.userData.structure = true;
  interior.add(roomFill);

  const roomAccent = new THREE.PointLight(pal.accent || 0xe879f9, neonRoom ? 0.32 : 0.12, Math.max(w, d) * 2.2, 1.5);
  roomAccent.position.set(iw * 0.3, roomH * 0.4, -id_ * 0.25);
  roomAccent.name = 'roomAccent';
  roomAccent.userData.structure = true;
  interior.add(roomAccent);

  building.userData.roomLamp = lamp;
  building.userData.roomFill = roomFill;
  building.userData.roomAccent = roomAccent;
}

/** Remove this building's interior lights so they stop counting toward the
 * scene's total PointLight budget once nobody is inside. */
function disposeRoomLights(building) {
  const interior = building.userData.interior;
  for (const key of ['roomLamp', 'roomFill', 'roomAccent']) {
    const light = building.userData[key];
    if (light) {
      interior?.remove(light);
      light.dispose?.();
      building.userData[key] = null;
    }
  }
}

/** Toggle building enter/exit visuals. Returns camera focus in world coords. */
export function setBuildingEntered(THREE, building, entered) {
  if (!building?.userData?.enterable) return null;
  building.visible = true;
  building.userData.entered = !!entered;
  if (building.userData.exterior) building.userData.exterior.visible = !entered;
  if (entered) ensureRoomLights(THREE, building);
  if (building.userData.interior) {
    building.userData.interior.visible = !!entered;
    building.userData.interior.traverse((c) => {
      if (c.isLight) c.visible = !!entered;
    });
  }
  if (building.userData.floorGrid) building.userData.floorGrid.visible = !!entered;
  if (building.userData.selectHalo) {
    building.userData.selectHalo.visible = !!building.userData.selected && !entered;
  }
  if (building.userData.pickVolume) building.userData.pickVolume.visible = !entered;

  const p = building.position;
  const dims = building.userData.dims || { h: 4, d: 5.5, w: 5.5 };
  if (entered) {
    // Corner loft view — see open floor + zones, not a packed closet
    const roomD = dims.id || dims.d || 10;
    const roomW = dims.iw || dims.w || 10;
    const roomH = dims.roomH || 5.5;
    const eyeY = Math.min(2.6, Math.max(1.7, roomH * 0.38));
    return {
      cam: {
        x: p.x + roomW * 0.28,
        y: eyeY,
        z: p.z + roomD * 0.42,
      },
      target: {
        x: p.x - roomW * 0.05,
        y: eyeY * 0.55,
        z: p.z - roomD * 0.12,
      },
    };
  }
  return {
    cam: { x: p.x + Math.max(10, dims.w * 1.6), y: Math.max(10, dims.h + 6), z: p.z + Math.max(12, dims.d * 1.8) },
    target: { x: p.x, y: 1.4, z: p.z },
  };
}

/** Force outdoor default for one building. */
export function resetBuildingVisual(building) {
  if (!building?.userData) return;
  building.visible = true;
  building.userData.entered = false;
  building.userData.selected = !!building.userData.selected;
  if (building.userData.exterior) building.userData.exterior.visible = true;
  if (building.userData.interior) {
    building.userData.interior.visible = false;
  }
  disposeRoomLights(building);
  if (building.userData.floorGrid) building.userData.floorGrid.visible = false;
  if (building.userData.pickVolume) building.userData.pickVolume.visible = true;
  if (building.userData.selectHalo) {
    building.userData.selectHalo.visible = !!building.userData.selected;
  }
  delete building.userData._hiddenForInterior;
}

/** Neon-orb tree (Massive Manas reel) — street props only, never inside buildings. */
export function createTree(THREE, seed = 1, theme = 'cyberpunk') {
  const T = themeOf(theme);
  const rnd = mulberry32(seed);
  const g = new THREE.Group();
  if (theme === 'cyberpunk') {
    const stemH = 0.85 + rnd() * 0.45;
    const stem = new THREE.Mesh(
      new THREE.CylinderGeometry(0.035, 0.06, stemH, 6),
      new THREE.MeshStandardMaterial({
        color: T.trunk,
        emissive: T.trunk,
        emissiveIntensity: 0.45,
        roughness: 0.4,
        metalness: 0.5,
      })
    );
    stem.position.y = stemH / 2;
    g.add(stem);
    const orbCol = T.foliage[seed % T.foliage.length];
    const orbR = 0.22 + rnd() * 0.14;
    const orb = new THREE.Mesh(
      new THREE.SphereGeometry(orbR, 12, 10),
      new THREE.MeshStandardMaterial({
        color: orbCol,
        emissive: orbCol,
        emissiveIntensity: 0.85,
        roughness: 0.28,
        metalness: 0.35,
        transparent: true,
        opacity: 0.92,
      })
    );
    orb.position.y = stemH + orbR * 0.55;
    g.add(orb);
    // No per-tree PointLight: with 150-250+ neon-orb trees in a full city,
    // one real light each pushed the fragment shader past
    // MAX_FRAGMENT_UNIFORM_VECTORS(1024) — WebGL then fails shader
    // compilation and renders affected meshes solid white (found live,
    // 2026-09-11). The emissive material + UnrealBloomPass already produce
    // the glow; no dynamic light is needed for a static decorative prop.
    g.userData.kind = 'tree';
    return g;
  }
  const trunkH = 0.7 + rnd() * 0.5;
  const trunk = new THREE.Mesh(
    new THREE.CylinderGeometry(0.08, 0.12, trunkH, 6),
    new THREE.MeshStandardMaterial({ color: T.trunk, roughness: 0.9 })
  );
  trunk.position.y = trunkH / 2;
  trunk.castShadow = true;
  g.add(trunk);
  const foliageCol = T.foliage[seed % T.foliage.length];
  const crown = new THREE.Mesh(
    new THREE.ConeGeometry(0.32 + rnd() * 0.12, 0.55 + rnd() * 0.2, 7),
    new THREE.MeshStandardMaterial({ color: foliageCol, roughness: 0.7 })
  );
  crown.position.y = trunkH + 0.25;
  g.add(crown);
  g.userData.kind = 'tree';
  return g;
}

export function createRoadTile(THREE, len = 1, width = 0.95, theme = 'cyberpunk') {
  const T = themeOf(theme);
  const g = new THREE.Group();
  const road = new THREE.Mesh(
    new THREE.BoxGeometry(width, 0.04, len),
    new THREE.MeshStandardMaterial({ color: T.asphalt, roughness: 0.95 })
  );
  road.position.y = 0.02;
  road.receiveShadow = true;
  g.add(road);
  const line = new THREE.Mesh(
    new THREE.BoxGeometry(0.06, 0.045, len * 0.7),
    new THREE.MeshStandardMaterial({
      color: T.lane,
      roughness: 0.4,
      emissive: theme === 'cyberpunk' ? T.lane : 0x000000,
      emissiveIntensity: theme === 'cyberpunk' ? 0.65 : 0,
    })
  );
  line.position.y = 0.045;
  g.add(line);
  return g;
}

/** Sidewalk / plaza. */
export function createSidewalk(THREE, w = 1, d = 1, theme = 'cyberpunk') {
  const T = themeOf(theme);
  const m = new THREE.Mesh(
    new THREE.BoxGeometry(w, 0.06, d),
    new THREE.MeshStandardMaterial({ color: T.sidewalk, roughness: 0.9 })
  );
  m.position.y = 0.03;
  m.receiveShadow = true;
  return m;
}

/**
 * Build street grid: roads on even lanes, sidewalks, trees on corners,
 * filler buildings on free cells not occupied by POI/blocked.
 */
export function populateCity(THREE, {
  group,
  gridW = 64,
  gridH = 64,
  blocked = [],
  pois = {},
  seed = 42,
  poiMeta = {},
  theme = 'cyberpunk',
  roads = false,
  wildernessMargin = 24,
}) {
  const T = themeOf(theme);
  const rnd = mulberry32(seed);
  const margin = Math.max(0, wildernessMargin | 0);
  const blockedSet = new Set(blocked.map(([x, y]) => `${x},${y}`));
  const poiCells = new Set(
    Object.values(pois).map((p) => `${p[0] | 0},${p[1] | 0}`)
  );
  const poiMeshes = [];
  /** Axis-aligned footprints — trees must stay outside these. */
  const occupied = [];
  const markOccupied = (cx, cz, w, d, pad = 0.55) => {
    occupied.push({ x: cx, z: cz, hw: w * 0.5 + pad, hd: d * 0.5 + pad });
  };
  const canPlant = (tx, tz) => {
    for (const o of occupied) {
      if (Math.abs(tx - o.x) < o.hw && Math.abs(tz - o.z) < o.hd) return false;
    }
    return true;
  };
  /** Full footprint clear of every occupied AABB (prevents building overlap). */
  const fitsBox = (cx, cz, w, d, pad = 0.35) => {
    const hw = w * 0.5 + pad;
    const hd = d * 0.5 + pad;
    for (const o of occupied) {
      if (Math.abs(cx - o.x) < hw + o.hw && Math.abs(cz - o.z) < hd + o.hd) return false;
    }
    return true;
  };
  const plantTree = (tx, tz, seedKey, scale = 1) => {
    if (!canPlant(tx, tz)) return false;
    const t = createTree(THREE, hashStr(String(seedKey)), theme);
    t.position.set(tx, 0, tz);
    t.scale.setScalar(scale);
    group.add(t);
    return true;
  };

  const grass = new THREE.Mesh(
    new THREE.PlaneGeometry(gridW + margin * 2 + 16, gridH + margin * 2 + 16),
    new THREE.MeshStandardMaterial({
      color: T.grass,
      roughness: theme === 'cyberpunk' ? 0.8 : 1,
      metalness: theme === 'cyberpunk' ? 0.25 : 0,
      emissive: theme === 'cyberpunk' ? 0x1a0a2e : 0x000000,
      emissiveIntensity: theme === 'cyberpunk' ? 0.2 : 0,
    })
  );
  grass.rotation.x = -Math.PI / 2;
  grass.position.set(gridW / 2, -0.01, gridH / 2);
  grass.receiveShadow = true;
  group.add(grass);

  // Soft wilderness ring markers (outside city)
  if (margin > 0 && theme === 'cyberpunk') {
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(Math.max(gridW, gridH) * 0.52, Math.max(gridW, gridH) * 0.52 + 0.35, 64),
      new THREE.MeshBasicMaterial({
        color: 0x34d399,
        transparent: true,
        opacity: 0.08,
        side: THREE.DoubleSide,
        depthWrite: false,
      })
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.set(gridW / 2, 0.04, gridH / 2);
    group.add(ring);
  }

  // Optional road grid (off by default — cyberpunk city uses neon grid helper instead)
  const step = 4;
  if (roads) {
    for (let x = 0; x < gridW; x += step) {
      for (let z = 0; z < gridH; z++) {
        const road = createRoadTile(THREE, 1, 0.9, theme);
        road.position.set(x + 0.5, 0, z + 0.5);
        group.add(road);
      }
    }
    for (let z = 0; z < gridH; z += step) {
      for (let x = 0; x < gridW; x++) {
        if (x % step === 0) continue;
        const road = createRoadTile(THREE, 1, 0.9, theme);
        road.rotation.y = Math.PI / 2;
        road.position.set(x + 0.5, 0, z + 0.5);
        group.add(road);
      }
    }
  }

  for (const [x, y] of blocked) {
    const park = new THREE.Mesh(
      new THREE.BoxGeometry(0.9, 0.08, 0.9),
      new THREE.MeshStandardMaterial({
        color: T.park,
        roughness: 0.95,
        emissive: theme === 'cyberpunk' ? 0x2e1065 : 0x000000,
        emissiveIntensity: theme === 'cyberpunk' ? 0.3 : 0,
      })
    );
    park.position.set(x + 0.5, 0.04, y + 0.5);
    park.receiveShadow = true;
    group.add(park);
    if (rnd() > 0.45) {
      plantTree(x + 0.5, y + 0.5, `${x},${y}`, 0.85 + rnd() * 0.35);
    }
  }

  // Place POIs largest-first; shrink footprint until no AABB overlap
  const poiEntries = Object.entries(pois).sort((a, b) => {
    const ha = poiMeta[a[0]]?.h || 3.5;
    const hb = poiMeta[b[0]]?.h || 3.5;
    return hb - ha;
  });
  for (const [name, p] of poiEntries) {
    const meta = poiMeta[name] || {
      label: name,
      h: 3.5 + rnd() * 3,
      caption: name,
    };
    const h = meta.h || 4;
    const facade =
      meta.color != null
        ? meta.color
        : T.facades[hashStr(name) % T.facades.length];
    // Screenshot-scale blocks with room for cyan bands
    let bw = Math.max(3.6, Math.min(5.2, 3.2 + (h || 3) * 0.38));
    let bd = bw * (0.88 + (hashStr(name) % 5) * 0.025);
    const cx = p[0];
    const cz = p[1];
    let guard = 0;
    while (!fitsBox(cx, cz, bw, bd, 0.45) && guard < 10) {
      bw *= 0.88;
      bd *= 0.88;
      guard++;
    }
    if (!fitsBox(cx, cz, bw, bd, 0.25)) {
      bw = Math.min(bw, 2.4);
      bd = Math.min(bd, 2.2);
    }
    const b = createBuilding(THREE, {
      w: bw,
      h: Math.max(h, 3.6),
      d: bd,
      seed: hashStr(name),
      theme,
      facade,
      interactiveMeta: { name, ...meta },
    });
    b.position.set(cx, 0, cz);
    group.add(b);
    markOccupied(cx, cz, bw, bd, 0.55);
    if (b.userData.hitMesh) poiMeshes.push(b.userData.hitMesh);

    const ringR = Math.max(bw, bd) * 0.5 + 1.35;
    for (let i = 0; i < 4; i++) {
      const ang = (i / 4) * Math.PI * 2 + 0.35;
      const sx = cx + Math.cos(ang) * ringR;
      const sz = cz + Math.sin(ang) * ringR;
      if (!canPlant(sx, sz)) continue;
      const sw = createSidewalk(THREE, 1.0, 1.0, theme);
      sw.position.set(sx, 0, sz);
      group.add(sw);
      plantTree(sx, sz, `${name}-t${i}`, 0.85 + rnd() * 0.25);
    }
  }

  // Filler buildings — only if FULL footprint is free
  let placed = 0;
  for (let attempt = 0; attempt < 700 && placed < 110; attempt++) {
    const x = 2 + Math.floor(rnd() * (gridW - 4));
    const z = 2 + Math.floor(rnd() * (gridH - 4));
    if (roads && (x % step === 0 || z % step === 0)) continue;
    const key = `${x},${z}`;
    if (blockedSet.has(key) || poiCells.has(key)) continue;
    let nearPoi = false;
    for (const pk of poiCells) {
      const [px, pz] = pk.split(',').map(Number);
      if (Math.abs(px - x) + Math.abs(pz - z) < 3) {
        nearPoi = true;
        break;
      }
    }
    if (nearPoi) continue;
    if (!roads && x % 4 === 0 && z % 4 === 0) continue;

    const fw = 1.6 + rnd() * 1.5;
    const fd = 1.6 + rnd() * 1.5;
    const fcx = x + 0.5;
    const fcz = z + 0.5;
    if (!fitsBox(fcx, fcz, fw, fd, 0.4)) continue;

    const fh = 2.2 + rnd() * 6.5;
    const fb = createBuilding(THREE, {
      w: fw,
      h: fh,
      d: fd,
      // >>> 0 forces unsigned: plain ^ can flip the sign bit, and
      // T.facades[seed % T.facades.length] with a NEGATIVE seed indexes with
      // a negative number (JS arrays return undefined, not a wrapped index)
      // -> bodyCol undefined -> MeshBasicMaterial defaults to solid white.
      // Found live 2026-09-11: every filler building's body mesh was white.
      seed: (hashStr(key) ^ seed) >>> 0,
      theme,
      enterable: false,
    });
    fb.position.set(fcx, 0, fcz);
    group.add(fb);
    markOccupied(fcx, fcz, fw, fd, 0.4);
    placed++;
  }

  // Street trees on free cells only (never on building footprints)
  let trees = 0;
  for (let attempt = 0; attempt < 400 && trees < 90; attempt++) {
    const x = 1 + Math.floor(rnd() * (gridW - 2));
    const z = 1 + Math.floor(rnd() * (gridH - 2));
    const tx = x + 0.5 + (rnd() - 0.5) * 0.3;
    const tz = z + 0.5 + (rnd() - 0.5) * 0.3;
    if (plantTree(tx, tz, `street-${x}-${z}-${attempt}`, 0.75 + rnd() * 0.35)) {
      trees++;
    }
  }

  // Sparse neon trees in wilderness ring (outside city footprint)
  if (margin > 0) {
    let wildTrees = 0;
    for (let attempt = 0; attempt < 220 && wildTrees < 48; attempt++) {
      const side = Math.floor(rnd() * 4);
      let wx, wz;
      if (side === 0) {
        wx = -margin + 2 + rnd() * (margin - 3);
        wz = rnd() * gridH;
      } else if (side === 1) {
        wx = gridW + 1 + rnd() * (margin - 3);
        wz = rnd() * gridH;
      } else if (side === 2) {
        wx = rnd() * gridW;
        wz = -margin + 2 + rnd() * (margin - 3);
      } else {
        wx = rnd() * gridW;
        wz = gridH + 1 + rnd() * (margin - 3);
      }
      if (plantTree(wx, wz, `wild-${side}-${attempt}`, 0.9 + rnd() * 0.55)) {
        wildTrees++;
      }
    }
  }

  return { poiMeshes };
}
