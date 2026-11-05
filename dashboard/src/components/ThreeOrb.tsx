import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';

interface ThreeOrbProps {
  activityLevel?: number; // 0.0 (idle) to 1.0 (speaking/active)
  systemState?: 'ONLINE' | 'STANDBY' | 'BUSY' | 'ERROR';
}

/**
 * Soft radial falloff sprite texture for glowing embers, satellites, and sparks.
 */
function createEmberTexture(): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = 64;
  canvas.height = 64;
  const ctx = canvas.getContext('2d');
  if (ctx) {
    const grad = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
    grad.addColorStop(0.0, 'rgba(255, 255, 255, 1.0)');
    grad.addColorStop(0.25, 'rgba(255, 225, 95, 0.95)');
    grad.addColorStop(0.55, 'rgba(255, 115, 20, 0.45)');
    grad.addColorStop(0.85, 'rgba(180, 40, 0, 0.12)');
    grad.addColorStop(1.0, 'rgba(0, 0, 0, 0.0)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 64, 64);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

/**
 * High-contrast, high-resolution HUD reticle texture for the primary circular aperture.
 * Rendered with vibrant solar gold and amber strokes matching the reference interface.
 */
function createPrimaryHudTexture(): THREE.CanvasTexture {
  const size = 1024;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  if (ctx) {
    const cx = size / 2;
    const cy = size / 2;

    ctx.clearRect(0, 0, size, size);

    // Track 1: Outer continuous hairline
    ctx.strokeStyle = 'rgba(255, 215, 95, 0.90)';
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.arc(cx, cy, 475, 0, Math.PI * 2);
    ctx.stroke();

    // Track 2: Heavy segmented arcs (12 segments with precision gaps)
    ctx.strokeStyle = 'rgba(255, 180, 35, 0.98)';
    ctx.lineWidth = 6;
    const numArcs = 12;
    for (let i = 0; i < numArcs; i++) {
      if (i % 2 === 0) {
        const start = (i / numArcs) * Math.PI * 2;
        const end = ((i + 0.74) / numArcs) * Math.PI * 2;
        ctx.beginPath();
        ctx.arc(cx, cy, 452, start, end);
        ctx.stroke();
      }
    }

    // Track 3: Radial degree tick marks (72 ticks)
    const numTicks = 72;
    for (let i = 0; i < numTicks; i++) {
      const angle = (i / numTicks) * Math.PI * 2;
      const isMajor = i % 6 === 0;
      const rInner = isMajor ? 388 : 412;
      const rOuter = 438;

      ctx.strokeStyle = isMajor
        ? 'rgba(255, 245, 160, 1.0)'
        : 'rgba(255, 205, 75, 0.88)';
      ctx.lineWidth = isMajor ? 3.8 : 2.0;

      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(angle) * rInner, cy + Math.sin(angle) * rInner);
      ctx.lineTo(cx + Math.cos(angle) * rOuter, cy + Math.sin(angle) * rOuter);
      ctx.stroke();
    }

    // Track 4: Directional chevron triangles (4 cardinal directions)
    const numTriangles = 4;
    for (let i = 0; i < numTriangles; i++) {
      const angle = (i / numTriangles) * Math.PI * 2;
      const r = 365;
      const tx = cx + Math.cos(angle) * r;
      const ty = cy + Math.sin(angle) * r;

      ctx.save();
      ctx.translate(tx, ty);
      ctx.rotate(angle + Math.PI / 2);
      ctx.fillStyle = 'rgba(255, 235, 110, 1.0)';
      ctx.beginPath();
      ctx.moveTo(0, -12);
      ctx.lineTo(9, 10);
      ctx.lineTo(-9, 10);
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    }

    // Track 5: Fine dashed circular groove
    ctx.strokeStyle = 'rgba(255, 210, 70, 0.9)';
    ctx.lineWidth = 2.5;
    ctx.setLineDash([7, 8]);
    ctx.beginPath();
    ctx.arc(cx, cy, 330, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);

    // Track 6: Inner bright ring bordering the collar
    ctx.strokeStyle = 'rgba(255, 248, 180, 1.0)';
    ctx.lineWidth = 3.5;
    ctx.beginPath();
    ctx.arc(cx, cy, 280, 0, Math.PI * 2);
    ctx.stroke();
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

/**
 * Secondary HUD track with bracketed arc segments and fine degree dots.
 */
function createSecondaryHudTexture(): THREE.CanvasTexture {
  const size = 512;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  if (ctx) {
    const cx = size / 2;
    const cy = size / 2;

    ctx.clearRect(0, 0, size, size);

    // 8-segment bracketed arcs
    ctx.strokeStyle = 'rgba(255, 210, 75, 0.92)';
    ctx.lineWidth = 4;
    const numBrackets = 8;
    for (let i = 0; i < numBrackets; i++) {
      const start = (i / numBrackets) * Math.PI * 2 + 0.05;
      const end = ((i + 0.52) / numBrackets) * Math.PI * 2 - 0.05;
      ctx.beginPath();
      ctx.arc(cx, cy, 230, start, end);
      ctx.stroke();
    }

    // Inner fine dotted track
    ctx.strokeStyle = 'rgba(255, 230, 100, 0.85)';
    ctx.lineWidth = 2.5;
    ctx.setLineDash([4, 6]);
    ctx.beginPath();
    ctx.arc(cx, cy, 182, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

/**
 * Starburst lens flare texture with horizontal anamorphic streak.
 */
function createGlintTexture(): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext('2d');
  if (ctx) {
    const cx = 128;
    const cy = 128;

    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, 64);
    grad.addColorStop(0.0, 'rgba(255, 255, 255, 1.0)');
    grad.addColorStop(0.25, 'rgba(255, 230, 110, 0.95)');
    grad.addColorStop(0.55, 'rgba(255, 140, 25, 0.4)');
    grad.addColorStop(1.0, 'rgba(0, 0, 0, 0.0)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 256, 256);

    const hGrad = ctx.createLinearGradient(0, cy, 256, cy);
    hGrad.addColorStop(0.0, 'rgba(255, 160, 30, 0.0)');
    hGrad.addColorStop(0.25, 'rgba(255, 220, 100, 0.70)');
    hGrad.addColorStop(0.5, 'rgba(255, 255, 255, 1.0)');
    hGrad.addColorStop(0.75, 'rgba(255, 220, 100, 0.70)');
    hGrad.addColorStop(1.0, 'rgba(255, 160, 30, 0.0)');
    ctx.fillStyle = hGrad;
    ctx.fillRect(0, cy - 4, 256, 8);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

/**
 * Common GLSL 3D Simplex noise functions.
 */
const simplexNoiseGLSL = `
  vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
  vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
  vec4 permute(vec4 x) { return mod289(((x*34.0)+1.0)*x); }
  vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

  float snoise(vec3 v) {
    const vec2 C = vec2(1.0/6.0, 1.0/3.0);
    const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
    vec3 i  = floor(v + dot(v, C.yyy));
    vec3 x0 = v - i + dot(i, C.xxx);
    vec3 g = step(x0.yzx, x0.xyz);
    vec3 l = 1.0 - g;
    vec3 i1 = min(g.xyz, l.zxy);
    vec3 i2 = max(g.xyz, l.zxy);
    vec3 x1 = x0 - i1 + C.xxx;
    vec3 x2 = x0 - i2 + C.yyy;
    vec3 x3 = x0 - D.yyy;
    i = mod289(i);
    vec4 p = permute(permute(permute(
              i.z + vec4(0.0, i1.z, i2.z, 1.0))
            + i.y + vec4(0.0, i1.y, i2.y, 1.0))
            + i.x + vec4(0.0, i1.x, i2.x, 1.0));
    float n_ = 0.142857142857;
    vec3 ns = n_ * D.wyz - D.xzx;
    vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
    vec4 x_ = floor(j * ns.z);
    vec4 y_ = floor(j - 7.0 * x_);
    vec4 x = x_ *ns.x + ns.yyyy;
    vec4 y = y_ *ns.x + ns.yyyy;
    vec4 h = 1.0 - abs(x) - abs(y);
    vec4 b0 = vec4(x.xy, y.xy);
    vec4 b1 = vec4(x.zw, y.zw);
    vec4 s0 = floor(b0)*2.0 + 1.0;
    vec4 s1 = floor(b1)*2.0 + 1.0;
    vec4 sh = -step(h, vec4(0.0));
    vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy;
    vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww;
    vec3 p0 = vec3(a0.xy, h.x);
    vec3 p1 = vec3(a0.zw, h.y);
    vec3 p2 = vec3(a1.xy, h.z);
    vec3 p3 = vec3(a1.zw, h.w);
    vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2, p2), dot(p3,p3)));
    p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
    vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
    m = m * m;
    return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
  }
`;

export const ThreeOrb: React.FC<ThreeOrbProps> = ({
  activityLevel = 0.2,
  systemState = 'ONLINE',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const animFrameId = useRef<number | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const width = container.clientWidth || 400;
    const height = container.clientHeight || 400;

    // Scene, Camera, Renderer
    const scene = new THREE.Scene();
    // Camera positioned at z = 8.6 to comfortably fit the complete inclined Saturn ring
    // and lateral soundwave equalizer wings inside the action stage viewport
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.set(0, 0, 8.6);

    const renderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias: true,
      powerPreference: 'high-performance',
    });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.35;
    container.appendChild(renderer.domElement);

    // Root Group
    const rootGroup = new THREE.Group();
    scene.add(rootGroup);

    // Procedural textures
    const emberTex = createEmberTexture();
    const primaryHudTex = createPrimaryHudTexture();
    const secondaryHudTex = createSecondaryHudTexture();
    const glintTex = createGlintTexture();

    // =========================================================================
    // LAYER A: DARK CENTRAL CORE (Event Horizon Void)
    // 3D sphere (radius 0.44) with deep obsidian bronze and subtle warm golden edge
    // =========================================================================
    const coreVertexShader = `
      varying vec3 vNormal;
      varying vec3 vPosition;
      void main() {
        vNormal = normalize(normalMatrix * normal);
        vPosition = (modelViewMatrix * vec4(position, 1.0)).xyz;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `;

    const coreFragmentShader = `
      varying vec3 vNormal;
      varying vec3 vPosition;
      void main() {
        vec3 viewDir = normalize(-vPosition);
        float fresnel = clamp(1.0 - abs(dot(viewDir, vNormal)), 0.0, 1.0);

        vec3 colObsidian = vec3(0.035, 0.020, 0.012);
        vec3 colBronze   = vec3(0.16, 0.09, 0.035);
        vec3 colEdge     = vec3(1.0, 0.85, 0.48);

        vec3 color = mix(colObsidian, colBronze, smoothstep(0.2, 0.75, fresnel));
        color = mix(color, colEdge, smoothstep(0.82, 1.0, fresnel));

        gl_FragColor = vec4(color, 1.0);
      }
    `;

    const coreGeo = new THREE.SphereGeometry(0.44, 36, 36);
    const coreMat = new THREE.ShaderMaterial({
      vertexShader: coreVertexShader,
      fragmentShader: coreFragmentShader,
      transparent: false,
      depthWrite: true,
    });
    const coreMesh = new THREE.Mesh(coreGeo, coreMat);
    coreMesh.renderOrder = 0;
    rootGroup.add(coreMesh);

    // =========================================================================
    // LAYER B: BURNING FIERY PLASMA COLLAR (Multi-Lobed Writhing Solar Fire)
    // Encircling the event horizon with 5-6 energetic lobes (radius 0.48 to 0.82)
    // =========================================================================
    const collarVertexShader = `
      varying vec2 vUv;
      varying vec3 vNormal;
      varying vec3 vPosition;
      uniform float uTime;
      ${simplexNoiseGLSL}

      void main() {
        vUv = uv;
        vNormal = normalize(normalMatrix * normal);

        // Calculate angle theta in the XY plane
        float theta = atan(position.y, position.x);
        
        // Multi-harmonic solar flare lobes (5 main lobes + 3 secondary lobes)
        float lobe1 = sin(5.0 * theta - uTime * 2.2) * 0.16;
        float lobe2 = cos(3.0 * theta + uTime * 1.6) * 0.10;
        float lobe3 = sin(8.0 * theta - uTime * 3.2) * 0.05;
        float lobeMod = 1.0 + lobe1 + lobe2 + lobe3;

        // Simplex 3D noise vertex displacement
        vec3 coord = position * 3.2 + vec3(0.0, uTime * 0.8, uTime * 0.5);
        float disp = snoise(coord) * 0.08;

        vec3 newPos = position;
        newPos.xy *= lobeMod;
        newPos += normal * disp;

        vPosition = (modelViewMatrix * vec4(newPos, 1.0)).xyz;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(newPos, 1.0);
      }
    `;

    const collarFragmentShader = `
      varying vec2 vUv;
      varying vec3 vNormal;
      varying vec3 vPosition;
      uniform float uTime;
      ${simplexNoiseGLSL}

      void main() {
        vec3 viewDir = normalize(-vPosition);
        float fresnel = clamp(1.0 - abs(dot(viewDir, vNormal)), 0.0, 1.0);

        // Blinding white-hot inner lip transitioning to solar gold and fiery red
        vec3 colWhiteHot = vec3(1.0, 0.99, 0.92);
        vec3 colSolar    = vec3(1.0, 0.80, 0.18);
        vec3 colOrange   = vec3(1.0, 0.44, 0.02);
        vec3 colDeepRed  = vec3(0.85, 0.15, 0.01);

        float edgeDist = abs(vUv.y - 0.5) * 2.0;

        // Internal turbulent flame noise
        vec3 flameCoord = vec3(vUv * 6.0, uTime * 0.7);
        float flame = snoise(flameCoord) * 0.35 + 0.65;

        vec3 color = mix(colWhiteHot, colSolar, smoothstep(0.0, 0.32, edgeDist));
        color = mix(color, colOrange, smoothstep(0.32, 0.72, edgeDist));
        color = mix(color, colDeepRed, smoothstep(0.72, 1.0, edgeDist));
        color *= flame;

        float alpha = clamp((1.0 - pow(edgeDist, 2.0)) * (fresnel * 0.4 + 0.6), 0.3, 0.98);
        gl_FragColor = vec4(color, alpha);
      }
    `;

    const collarMeshGeo = new THREE.TorusGeometry(0.62, 0.15, 32, 96);
    const collarUniforms = { uTime: { value: 0 } };
    const collarMeshMat = new THREE.ShaderMaterial({
      vertexShader: collarVertexShader,
      fragmentShader: collarFragmentShader,
      uniforms: collarUniforms,
      transparent: true,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const collarMesh = new THREE.Mesh(collarMeshGeo, collarMeshMat);
    collarMesh.position.z = 0.01;
    collarMesh.renderOrder = 1;
    rootGroup.add(collarMesh);

    // =========================================================================
    // LAYER C: FUTURISTIC CIRCULAR HUD DISC ASSEMBLY
    // High-contrast golden reticle with bronze backing disc
    // =========================================================================
    const hudBackingGeo = new THREE.RingGeometry(0.52, 1.62, 64);
    const hudBackingMat = new THREE.MeshBasicMaterial({
      color: new THREE.Color('#140a03'),
      transparent: true,
      opacity: 0.52,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const hudBackingMesh = new THREE.Mesh(hudBackingGeo, hudBackingMat);
    hudBackingMesh.position.z = 0.02;
    hudBackingMesh.renderOrder = 1;
    rootGroup.add(hudBackingMesh);

    // Primary HUD Disc (radius 0.76 to 1.58, z = 0.04)
    const hudPrimaryGeo = new THREE.RingGeometry(0.76, 1.58, 96);
    const hudPrimaryMat = new THREE.MeshBasicMaterial({
      map: primaryHudTex,
      transparent: true,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
      depthWrite: false,
      opacity: 0.95,
    });
    const hudPrimaryMesh = new THREE.Mesh(hudPrimaryGeo, hudPrimaryMat);
    hudPrimaryMesh.position.z = 0.04;
    hudPrimaryMesh.renderOrder = 2;
    rootGroup.add(hudPrimaryMesh);

    // Secondary Bracketed Arc Track (radius 0.95 to 1.45, z = -0.03, tilt x = 0.10)
    const hudSecondaryGeo = new THREE.RingGeometry(0.95, 1.45, 72);
    const hudSecondaryMat = new THREE.MeshBasicMaterial({
      map: secondaryHudTex,
      transparent: true,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
      depthWrite: false,
      opacity: 0.85,
    });
    const hudSecondaryMesh = new THREE.Mesh(hudSecondaryGeo, hudSecondaryMat);
    hudSecondaryMesh.position.z = -0.03;
    hudSecondaryMesh.rotation.x = 0.10;
    hudSecondaryMesh.renderOrder = 2;
    rootGroup.add(hudSecondaryMesh);

    // Tertiary Outer Hairline Guide (radius 1.58 to 1.62, z = 0.05)
    const hudGuideGeo = new THREE.RingGeometry(1.58, 1.62, 96);
    const hudGuideMat = new THREE.MeshBasicMaterial({
      color: new THREE.Color('#f5af37'),
      transparent: true,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
      depthWrite: false,
      opacity: 0.80,
    });
    const hudGuideMesh = new THREE.Mesh(hudGuideGeo, hudGuideMat);
    hudGuideMesh.position.z = 0.05;
    hudGuideMesh.renderOrder = 2;
    rootGroup.add(hudGuideMesh);

    // =========================================================================
    // LAYER D: DUAL-PASS VOLUMETRIC PLASMA SHELL (BackSide + FrontSide)
    // Continuous 3D noise-displaced plasma with realistic limb scattering
    // =========================================================================
    const plasmaVertexShader = `
      varying vec3 vNormal;
      varying vec3 vPosition;
      varying vec3 vWorldPosition;
      uniform float uTime;
      ${simplexNoiseGLSL}

      void main() {
        vNormal = normalize(normalMatrix * normal);
        vec3 noiseCoord = position * 1.6 + vec3(0.0, uTime * 0.35, uTime * 0.20);
        float disp = snoise(noiseCoord) * 0.14 + snoise(noiseCoord * 2.8) * 0.06;
        vec3 newPos = position + normal * disp;
        vWorldPosition = newPos;
        vPosition = (modelViewMatrix * vec4(newPos, 1.0)).xyz;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(newPos, 1.0);
      }
    `;

    // 1. Back-Shell (Inner rear bowl: deeper ruby/crimson-amber tones)
    const plasmaBackFragmentShader = `
      varying vec3 vNormal;
      varying vec3 vPosition;
      varying vec3 vWorldPosition;
      uniform float uTime;
      ${simplexNoiseGLSL}

      void main() {
        vec3 viewDir = normalize(-vPosition);
        float fresnel = clamp(1.0 - abs(dot(viewDir, vNormal)), 0.0, 1.0);
        float rimGlow = pow(fresnel, 2.5);

        vec3 coord = vWorldPosition * 2.2 + vec3(0.0, uTime * 0.25, 0.0);
        float flame = snoise(coord) * 0.65 + snoise(coord * 2.5) * 0.35;
        flame = clamp(flame * 0.5 + 0.5, 0.0, 1.0);

        vec3 colDeepCrimson = vec3(0.65, 0.12, 0.01);
        vec3 colDeepAmber   = vec3(0.88, 0.32, 0.03);
        vec3 color = mix(colDeepCrimson, colDeepAmber, flame);

        float alpha = rimGlow * 0.40 + flame * 0.12;
        gl_FragColor = vec4(color, alpha);
      }
    `;

    const plasmaBackGeo = new THREE.SphereGeometry(1.95, 48, 48);
    const plasmaBackUniforms = { uTime: { value: 0 } };
    const plasmaBackMat = new THREE.ShaderMaterial({
      vertexShader: plasmaVertexShader,
      fragmentShader: plasmaBackFragmentShader,
      uniforms: plasmaBackUniforms,
      transparent: true,
      blending: THREE.AdditiveBlending,
      side: THREE.BackSide,
      depthWrite: false,
    });
    const plasmaBackMesh = new THREE.Mesh(plasmaBackGeo, plasmaBackMat);
    plasmaBackMesh.renderOrder = 1; // Render behind HUD
    rootGroup.add(plasmaBackMesh);

    // 2. Front-Shell (Outer luminous front dome: vibrant amber-gold wisps + corona)
    const plasmaFrontFragmentShader = `
      varying vec3 vNormal;
      varying vec3 vPosition;
      varying vec3 vWorldPosition;
      uniform float uTime;
      ${simplexNoiseGLSL}

      void main() {
        vec3 viewDir = normalize(-vPosition);
        float fresnel = clamp(1.0 - abs(dot(viewDir, vNormal)), 0.0, 1.0);
        float rimGlow = pow(fresnel, 2.0);

        // Multi-frequency turbulent wisps with domain warping
        vec3 coord = vWorldPosition * 2.0 + vec3(0.0, uTime * 0.30, uTime * 0.15);
        float n1 = snoise(coord);
        float n2 = snoise(coord * 2.4 + vec3(n1 * 0.4));
        float flame = clamp((n1 * 0.65 + n2 * 0.35) * 0.5 + 0.5, 0.0, 1.0);

        vec3 colDeepAmber = vec3(0.90, 0.30, 0.02);
        vec3 colSolarGold = vec3(1.0, 0.78, 0.18);
        vec3 colWarmIvory = vec3(1.0, 0.96, 0.85);

        vec3 color = mix(colDeepAmber, colSolarGold, flame);
        color = mix(color, colWarmIvory, rimGlow * flame * 0.7);

        // Negative space: low alpha in center to reveal HUD clearly; rich glow at rim
        float alpha = rimGlow * 0.58 + flame * 0.16 * (fresnel * 0.8 + 0.2);
        gl_FragColor = vec4(color, alpha);
      }
    `;

    const plasmaFrontGeo = new THREE.SphereGeometry(2.02, 48, 48);
    const plasmaFrontUniforms = { uTime: { value: 0 } };
    const plasmaFrontMat = new THREE.ShaderMaterial({
      vertexShader: plasmaVertexShader,
      fragmentShader: plasmaFrontFragmentShader,
      uniforms: plasmaFrontUniforms,
      transparent: true,
      blending: THREE.AdditiveBlending,
      side: THREE.FrontSide,
      depthWrite: false,
    });
    const plasmaFrontMesh = new THREE.Mesh(plasmaFrontGeo, plasmaFrontMat);
    plasmaFrontMesh.renderOrder = 3; // Render in front of HUD
    rootGroup.add(plasmaFrontMesh);

    // =========================================================================
    // LAYER E: CRINKLED PERIMETER LIGHTNING FILAMENTS & CORONAL CRESTS
    // Undulating 3D curves hugging the outer perimeter (r ~ 2.04 to 2.12)
    // =========================================================================
    const createPerimeterLightning = (
      baseRadius: number,
      startAngle: number,
      endAngle: number,
      tubeR: number,
      color: string,
      segments: number = 72
    ) => {
      const curvePoints: THREE.Vector3[] = [];
      for (let i = 0; i <= segments; i++) {
        const frac = i / segments;
        const theta = startAngle + frac * (endAngle - startAngle);
        const crinkle =
          Math.sin(frac * 18.0) * 0.05 +
          Math.cos(frac * 32.0) * 0.03 +
          Math.sin(frac * 56.0) * 0.015;
        const r = baseRadius + crinkle;
        const zWobble = Math.sin(frac * 10.0) * 0.12;

        curvePoints.push(
          new THREE.Vector3(
            r * Math.cos(theta),
            r * Math.sin(theta),
            zWobble
          )
        );
      }
      const curve = new THREE.CatmullRomCurve3(curvePoints);
      const tubeGeo = new THREE.TubeGeometry(curve, segments, tubeR, 6, false);
      const tubeMat = new THREE.MeshBasicMaterial({
        color: new THREE.Color(color),
        transparent: true,
        opacity: 0.95,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      const mesh = new THREE.Mesh(tubeGeo, tubeMat);
      mesh.renderOrder = 4;
      rootGroup.add(mesh);
      return { mesh, tubeGeo, tubeMat };
    };

    // Crest 1: Upper-right solar filament connecting to the flare glint
    const lightningTop = createPerimeterLightning(2.07, 0.15, Math.PI * 0.88, 0.024, '#ffe494');
    // Crest 2: Bottom-left fiery electric filament
    const lightningBottom = createPerimeterLightning(2.05, -0.25, -Math.PI * 0.85, 0.026, '#ff5500');
    // Crest 3: Left coronal crest (Deep crimson-amber)
    const lightningLeft = createPerimeterLightning(2.09, Math.PI * 0.72, Math.PI * 1.28, 0.020, '#d82c00');

    // =========================================================================
    // LAYER F: INCLINED SATURN-LIKE EQUATORIAL RINGS & LATERAL EQUALIZERS
    // Wide horizontal orbital silhouette with restrained equalizer ticks strictly on left/right wings
    // =========================================================================
    const equatorialRingGroup = new THREE.Group();
    equatorialRingGroup.rotation.x = Math.PI * 0.36; // ~26° inclination
    equatorialRingGroup.rotation.y = 0.10;
    rootGroup.add(equatorialRingGroup);

    // Track 1: Outer Fiery Neon Ribbon Ring (width 0.14)
    const outerNeonGeo = new THREE.RingGeometry(3.02, 3.16, 96);
    const outerNeonMat = new THREE.MeshBasicMaterial({
      color: new THREE.Color('#ff4500'),
      transparent: true,
      opacity: 0.88,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const outerNeonMesh = new THREE.Mesh(outerNeonGeo, outerNeonMat);
    outerNeonMesh.renderOrder = 3;
    equatorialRingGroup.add(outerNeonMesh);

    // Track 2: Mid Golden Technical Ring
    const midTrackGeo = new THREE.RingGeometry(2.74, 2.80, 96);
    const midTrackMat = new THREE.MeshBasicMaterial({
      color: new THREE.Color('#ffb830'),
      transparent: true,
      opacity: 0.82,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const midTrackMesh = new THREE.Mesh(midTrackGeo, midTrackMat);
    midTrackMesh.renderOrder = 3;
    equatorialRingGroup.add(midTrackMesh);

    // Track 3: Inner Segmented Track
    const innerTrackGeo = new THREE.RingGeometry(2.46, 2.50, 96);
    const innerTrackMat = new THREE.MeshBasicMaterial({
      color: new THREE.Color('#ffd57a'),
      transparent: true,
      opacity: 0.70,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const innerTrackMesh = new THREE.Mesh(innerTrackGeo, innerTrackMat);
    innerTrackMesh.renderOrder = 3;
    equatorialRingGroup.add(innerTrackMesh);

    // Track 4: SUBTLE RADIAL EQUALIZER TICKS (STRICTLY ON HORIZONTAL LATERAL WINGS)
    // Steep falloff pow(abs(cos(theta)), 8.0) ensures ticks exist ONLY on the far left and far right tips!
    // Absolute ZERO ticks on the top, bottom, or front!
    const numSoundwaveBars = 160;
    const soundwaveGroup = new THREE.Group();
    equatorialRingGroup.add(soundwaveGroup);

    const swBarGeo = new THREE.PlaneGeometry(0.020, 1.0);
    const swBarMat = new THREE.MeshBasicMaterial({
      color: new THREE.Color('#ffe27a'),
      transparent: true,
      opacity: 0.88,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
      depthWrite: false,
    });

    const swMeshes: THREE.Mesh[] = [];
    const swBaseR = 2.80;
    for (let i = 0; i < numSoundwaveBars; i++) {
      const mesh = new THREE.Mesh(swBarGeo, swBarMat);
      const theta = (i / numSoundwaveBars) * Math.PI * 2;
      mesh.position.set(Math.cos(theta) * swBaseR, Math.sin(theta) * swBaseR, 0);
      mesh.rotation.z = theta - Math.PI / 2;
      soundwaveGroup.add(mesh);
      swMeshes.push(mesh);
    }

    // Track 5: Orbiting Comet Satellites (Flowing clockwise along ring)
    const numSatellites = 3;
    const satGeo = new THREE.BufferGeometry();
    const satPositions = new Float32Array(numSatellites * 3);
    satGeo.setAttribute('position', new THREE.BufferAttribute(satPositions, 3));
    const satMat = new THREE.PointsMaterial({
      map: emberTex,
      size: 0.40,
      color: new THREE.Color('#fff5b0'),
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const satellites = new THREE.Points(satGeo, satMat);
    satellites.renderOrder = 5;
    equatorialRingGroup.add(satellites);

    // =========================================================================
    // LAYER G: SURROUNDING ENERGY PARTICLES & SPECULAR GLINT
    // =========================================================================
    // Organic Surface Embers (800 points drifting across plasma surface)
    const shellParticleCount = 800;
    const shellParticleGeo = new THREE.BufferGeometry();
    const shellPositions = new Float32Array(shellParticleCount * 3);
    const shellColors = new Float32Array(shellParticleCount * 3);
    const shellThetas = new Float32Array(shellParticleCount);
    const shellPhis = new Float32Array(shellParticleCount);
    const shellRadii = new Float32Array(shellParticleCount);
    const shellSpeeds = new Float32Array(shellParticleCount);

    const cSolarGold = new THREE.Color('#ffc840');
    const cFieryOrange = new THREE.Color('#ff6510');
    const cDeepRed = new THREE.Color('#d02500');

    for (let i = 0; i < shellParticleCount; i++) {
      const r = 1.96 + Math.random() * 0.16;
      const theta = Math.random() * Math.PI * 2;
      const phi = (Math.random() - 0.5) * Math.PI * 0.88;

      shellRadii[i] = r;
      shellThetas[i] = theta;
      shellPhis[i] = phi;
      shellSpeeds[i] = (0.22 + Math.random() * 0.30) * (Math.random() > 0.5 ? 1 : -1);

      shellPositions[i * 3] = r * Math.cos(phi) * Math.cos(theta);
      shellPositions[i * 3 + 1] = r * Math.sin(phi);
      shellPositions[i * 3 + 2] = r * Math.cos(phi) * Math.sin(theta);

      const mix = Math.random();
      const col =
        mix > 0.5
          ? cSolarGold.clone().lerp(cFieryOrange, (mix - 0.5) * 2)
          : cFieryOrange.clone().lerp(cDeepRed, mix * 2);

      shellColors[i * 3] = col.r;
      shellColors[i * 3 + 1] = col.g;
      shellColors[i * 3 + 2] = col.b;
    }
    shellParticleGeo.setAttribute('position', new THREE.BufferAttribute(shellPositions, 3));
    shellParticleGeo.setAttribute('color', new THREE.BufferAttribute(shellColors, 3));
    const shellParticleMat = new THREE.PointsMaterial({
      map: emberTex,
      size: 0.065,
      vertexColors: true,
      transparent: true,
      opacity: 0.85,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const shellParticles = new THREE.Points(shellParticleGeo, shellParticleMat);
    shellParticles.renderOrder = 4;
    rootGroup.add(shellParticles);

    // Orbital Stream Particles (250 points flowing clockwise along the ring plane)
    const ringParticleCount = 250;
    const ringParticleGeo = new THREE.BufferGeometry();
    const ringPositions = new Float32Array(ringParticleCount * 3);
    const ringThetas = new Float32Array(ringParticleCount);
    const ringRadii = new Float32Array(ringParticleCount);
    const ringSpeeds = new Float32Array(ringParticleCount);

    for (let i = 0; i < ringParticleCount; i++) {
      const r = 2.62 + Math.random() * 0.42;
      const theta = Math.random() * Math.PI * 2;
      ringRadii[i] = r;
      ringThetas[i] = theta;
      ringSpeeds[i] = 0.35 + Math.random() * 0.35;

      ringPositions[i * 3] = Math.cos(theta) * r;
      ringPositions[i * 3 + 1] = Math.sin(theta) * r;
      ringPositions[i * 3 + 2] = (Math.random() - 0.5) * 0.10;
    }
    ringParticleGeo.setAttribute('position', new THREE.BufferAttribute(ringPositions, 3));
    const ringParticleMat = new THREE.PointsMaterial({
      map: emberTex,
      size: 0.065,
      color: new THREE.Color('#ffc830'),
      transparent: true,
      opacity: 0.80,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const ringParticles = new THREE.Points(ringParticleGeo, ringParticleMat);
    ringParticles.renderOrder = 4;
    equatorialRingGroup.add(ringParticles);

    // Specular Starburst Flare Glint (at ~2 o'clock, x: 1.35, y: 1.25, z: 1.05)
    const glintGeo = new THREE.PlaneGeometry(1.85, 1.85);
    const glintMat = new THREE.MeshBasicMaterial({
      map: glintTex,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      opacity: 0.98,
    });
    const glintMesh = new THREE.Mesh(glintGeo, glintMat);
    glintMesh.position.set(1.35, 1.25, 1.05);
    glintMesh.renderOrder = 5;
    rootGroup.add(glintMesh);

    // =========================================================================
    // ANIMATION LOOP (Elapsed-Time Based, Frame-Rate Independent)
    // =========================================================================
    const clock = new THREE.Clock();

    const animate = () => {
      animFrameId.current = requestAnimationFrame(animate);

      const delta = clock.getDelta();
      const elapsed = clock.getElapsedTime();

      // 1. Animate Burning Plasma Collar & Volumetric Plasma Spheres
      collarUniforms.uTime.value = elapsed;
      collarMesh.rotation.z -= delta * 0.35;
      plasmaBackUniforms.uTime.value = elapsed;
      plasmaFrontUniforms.uTime.value = elapsed;

      // 2. Rotate Circular HUD Discs
      hudPrimaryMesh.rotation.z -= delta * 0.10;   // Primary disc slow clockwise
      hudSecondaryMesh.rotation.z += delta * 0.07; // Secondary disc counter-clockwise
      hudGuideMesh.rotation.z -= delta * 0.03;     // Outer hairline slow clockwise

      // 3. Animate Outer Crinkled Lightning Filaments
      lightningTop.mesh.rotation.z = Math.sin(elapsed * 0.5) * 0.03;
      lightningBottom.mesh.rotation.z = Math.cos(elapsed * 0.45) * 0.03;
      lightningLeft.mesh.rotation.z = Math.sin(elapsed * 0.6) * 0.04;

      // 4. Stable Inclined Ring System with CLOCKWISE Visual Flow
      // Outer ring and satellites flow clockwise without tumbling the ring coordinate frame
      const ringFlowRate = 0.35;

      // 4b. Lateral Soundwave Equalizer Ticks (STRICTLY ON HORIZONTAL LATERAL WINGS)
      // pow(abs(cos(theta)), 8.0) guarantees zero bars across top, bottom, or front!
      const activePulseFactor = activityLevel > 0.4 ? 1.5 : 0.8;
      for (let i = 0; i < numSoundwaveBars; i++) {
        const theta = (i / numSoundwaveBars) * Math.PI * 2;
        const lateralFactor = Math.pow(Math.abs(Math.cos(theta)), 8.0);
        
        if (lateralFactor < 0.005) {
          swMeshes[i].visible = false;
          continue;
        }
        
        swMeshes[i].visible = true;
        const dynamicPulse = Math.sin(theta * 10.0 - elapsed * 5.0) * 0.5 + 0.5;
        const barH = lateralFactor * (0.09 + dynamicPulse * 0.18 * activePulseFactor);
        swMeshes[i].scale.set(1.0, barH, 1.0);
        const rPos = swBaseR + barH * 0.5;
        swMeshes[i].position.set(Math.cos(theta) * rPos, Math.sin(theta) * rPos, 0);
      }

      // 4c. Satellites traversing clockwise along ring
      const satPosAttr = satGeo.attributes.position as THREE.BufferAttribute;
      for (let i = 0; i < numSatellites; i++) {
        // Clockwise motion along ring plane: minus sign on angle
        const sAngle = -elapsed * ringFlowRate * 1.5 - (i * Math.PI * 2) / numSatellites;
        const sR = 3.09;
        satPosAttr.setXYZ(i, Math.cos(sAngle) * sR, Math.sin(sAngle) * sR, 0);
      }
      satPosAttr.needsUpdate = true;

      // 5. Animate Shell Particles & Stream Particles (Flowing Clockwise)
      const sPosAttr = shellParticleGeo.attributes.position as THREE.BufferAttribute;
      for (let i = 0; i < shellParticleCount; i++) {
        shellThetas[i] += shellSpeeds[i] * delta * 0.30;
        const r = shellRadii[i];
        const theta = shellThetas[i];
        const phi = shellPhis[i] + Math.sin(elapsed * 0.5 + i) * 0.015;

        sPosAttr.setXYZ(
          i,
          r * Math.cos(phi) * Math.cos(theta),
          r * Math.sin(phi),
          r * Math.cos(phi) * Math.sin(theta)
        );
      }
      sPosAttr.needsUpdate = true;

      const rPosAttr = ringParticleGeo.attributes.position as THREE.BufferAttribute;
      for (let i = 0; i < ringParticleCount; i++) {
        // Stream particles flow clockwise: minus sign
        ringThetas[i] -= ringSpeeds[i] * delta * ringFlowRate;
        const r = ringRadii[i];
        const theta = ringThetas[i];
        rPosAttr.setXYZ(
          i,
          Math.cos(theta) * r,
          Math.sin(theta) * r,
          Math.sin(elapsed * 1.8 + i) * 0.02
        );
      }
      rPosAttr.needsUpdate = true;

      // 6. Pulse Top-Right Specular Flare Glint
      const glintScale = 1.0 + Math.sin(elapsed * 3.5) * 0.08;
      glintMesh.scale.set(glintScale, glintScale, glintScale);

      // Subtle atmospheric floating motion of root assembly
      rootGroup.rotation.y = Math.sin(elapsed * 0.25) * 0.03;
      rootGroup.rotation.x = Math.cos(elapsed * 0.20) * 0.025;

      renderer.render(scene, camera);
    };

    animate();

    // Window / Container Resize Handling
    const handleResize = () => {
      if (!container) return;
      const newWidth = container.clientWidth;
      const newHeight = container.clientHeight;
      if (newWidth === 0 || newHeight === 0) return;
      camera.aspect = newWidth / newHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(newWidth, newHeight);
    };

    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(container);

    // =========================================================================
    // CLEANUP ON UNMOUNT (Full WebGL Resource Disposal)
    // =========================================================================
    return () => {
      if (animFrameId.current) cancelAnimationFrame(animFrameId.current);
      resizeObserver.disconnect();

      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }

      renderer.dispose();

      // Geometries
      coreGeo.dispose();
      collarMeshGeo.dispose();
      hudBackingGeo.dispose();
      hudPrimaryGeo.dispose();
      hudSecondaryGeo.dispose();
      hudGuideGeo.dispose();
      plasmaBackGeo.dispose();
      plasmaFrontGeo.dispose();
      lightningTop.tubeGeo.dispose();
      lightningBottom.tubeGeo.dispose();
      lightningLeft.tubeGeo.dispose();
      outerNeonGeo.dispose();
      midTrackGeo.dispose();
      innerTrackGeo.dispose();
      swBarGeo.dispose();
      satGeo.dispose();
      shellParticleGeo.dispose();
      ringParticleGeo.dispose();
      glintGeo.dispose();

      // Materials
      coreMat.dispose();
      collarMeshMat.dispose();
      hudBackingMat.dispose();
      hudPrimaryMat.dispose();
      hudSecondaryMat.dispose();
      hudGuideMat.dispose();
      plasmaBackMat.dispose();
      plasmaFrontMat.dispose();
      lightningTop.tubeMat.dispose();
      lightningBottom.tubeMat.dispose();
      lightningLeft.tubeMat.dispose();
      outerNeonMat.dispose();
      midTrackMat.dispose();
      innerTrackMat.dispose();
      swBarMat.dispose();
      satMat.dispose();
      shellParticleMat.dispose();
      ringParticleMat.dispose();
      glintMat.dispose();

      // Textures
      emberTex.dispose();
      primaryHudTex.dispose();
      secondaryHudTex.dispose();
      glintTex.dispose();
    };
  }, [activityLevel, systemState]);

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height: '100%',
        position: 'relative',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    />
  );
};
