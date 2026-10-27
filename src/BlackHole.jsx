import { useEffect, useRef, useState } from 'react'
import usePrefersReducedMotion from './usePrefersReducedMotion'

const VERTEX_SHADER = `
  attribute vec2 aPosition;
  void main() {
    gl_Position = vec4(aPosition, 0.0, 1.0);
  }
`

// Exact Schwarzschild photon geodesics via the Binet equation, the same
// core technique used by Adriwin06/black-hole (github.com/Adriwin06/black-hole,
// a fork of oseiskar/black-hole): with u = 1/r and M = r_s/2 = 0.5,
//   d²u/dφ² = -u + 3Mu² = -u + 1.5u²
// is the *exact* null-geodesic equation for a non-spinning hole — not an
// approximation. Because it's parametrised by the swept angle φ rather than
// arc length, a photon's 3D position at any φ is just
//   pos(φ) = (cos(φ)·n̂ + sin(φ)·t̂) / u(φ)
// where n̂, t̂ span the (always-planar) orbit established once from the
// camera position and initial ray direction. That single fact is what
// replaces last version's inverse-cube bending hack: same disk-crossing /
// beaming / starfield code as before, just fed by a physically exact path,
// so higher-order lensed images near the photon sphere now emerge from the
// integration itself rather than a separate closest-approach heuristic.
const FRAGMENT_SHADER = `
  precision highp float;

  uniform vec2 uResolution;
  uniform float uTime;

  // ---------------------------------------------------------------------
  // Tunables — adjust the look here without touching the logic below.
  // HORIZON_R and PHOTON_R are physical constants of the Schwarzschild
  // solution in these units (r_s = 1), not stylistic knobs.
  // ---------------------------------------------------------------------
  const float INCLINATION     = 0.34;   // disk tilt off edge-on, radians
  const float ROTATION_SPEED  = 0.045;  // camera drift speed
  const float DISK_INNER      = 2.6;    // inner radius, in horizon radii (~ISCO)
  const float DISK_OUTER      = 9.0;    // outer radius, in horizon radii
  const float BLOOM_INTENSITY = 1.6;
  const float HORIZON_R       = 1.0;    // event horizon radius (= r_s)
  const float PHOTON_R        = 1.5;    // photon sphere radius -> the bright ring
  const vec3  DISK_HOT        = vec3(0.85, 0.97, 1.0);  // near-ISCO: blue-white
  const vec3  DISK_COOL       = vec3(1.0, 0.55, 0.22);  // outer edge: orange-red
  const int   RAY_STEPS       = 120;    // finer integration for cleaner photon-ring detail
  const float MAX_REVOLUTIONS = 2.15;   // retain additional higher-order lensed images
  // ---------------------------------------------------------------------

  float hash21(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
  }

  float valueNoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = hash21(i);
    float b = hash21(i + vec2(1.0, 0.0));
    float c = hash21(i + vec2(0.0, 1.0));
    float d = hash21(i + vec2(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
  }

  float fbm2(vec2 p) {
    float value = 0.0;
    float amplitude = 0.5;
    for (int i = 0; i < 4; i++) {
      value += amplitude * valueNoise(p);
      p = p * 2.03 + vec2(7.1, 3.7);
      amplitude *= 0.5;
    }
    return value;
  }

  // Procedural starfield sampled straight from a ray direction — no texture.
  vec3 starField(vec3 dir) {
    vec2 uv = dir.xy / (1.0 + abs(dir.z)) * 420.0;
    vec2 cell = floor(uv);
    vec2 f = fract(uv);
    float h = hash21(cell);
    float star = 0.0;
    if (h > 0.985) {
      vec2 starPos = vec2(hash21(cell + 1.0), hash21(cell + 7.0));
      float d = length(f - starPos);
      float size = mix(0.02, 0.09, hash21(cell + 3.0));
      star = (1.0 - smoothstep(0.0, size, d)) * mix(0.35, 1.0, hash21(cell + 9.0));
    }
    vec3 tint = mix(vec3(0.75, 0.85, 1.0), vec3(1.0, 0.92, 0.82), hash21(cell + 13.0));
    return vec3(star) * tint;
  }

  // The exact Schwarzschild Binet acceleration: d²u/dφ² = -u + 1.5u².
  float geodesicAccel(float u) {
    return -u + 1.5 * u * u;
  }

  // Classic RK4 step for the (u, du/dφ) system, one φ-increment at a time.
  void integrateStep(inout float u, inout float du, float h) {
    float k1u = du;
    float k1du = geodesicAccel(u);

    float u2 = u + 0.5 * h * k1u;
    float du2 = du + 0.5 * h * k1du;
    float k2u = du2;
    float k2du = geodesicAccel(u2);

    float u3 = u + 0.5 * h * k2u;
    float du3 = du + 0.5 * h * k2du;
    float k3u = du3;
    float k3du = geodesicAccel(u3);

    float u4 = u + h * k3u;
    float du4 = du + h * k3du;
    float k4u = du4;
    float k4du = geodesicAccel(u4);

    u += (h / 6.0) * (k1u + 2.0 * k2u + 2.0 * k3u + k4u);
    du += (h / 6.0) * (k1du + 2.0 * k2du + 2.0 * k3du + k4du);
  }

  // Shades a single disk-plane crossing between two nearby path points, or
  // returns black if the segment doesn't cross the disk / falls outside its
  // radii. Factored out so the photon-sphere region can call it several
  // times per step on sub-segments (see below) instead of once on the
  // whole step.
  vec3 diskCrossingColor(vec3 a, vec3 b, vec3 diskNormal, float time) {
    float d0 = dot(a, diskNormal);
    float d1 = dot(b, diskNormal);
    if (d0 * d1 >= 0.0) return vec3(0.0);
    float t = d0 / (d0 - d1);
    vec3 hit = mix(a, b, t);
    float rad = length(hit);
    if (rad <= DISK_INNER || rad >= DISK_OUTER) return vec3(0.0);

    float rn = clamp((rad - DISK_INNER) / (DISK_OUTER - DISK_INNER), 0.0, 1.0);
    vec3 diskCol = mix(DISK_HOT, DISK_COOL, pow(rn, 0.48));

    // Coordinates in the tilted disk plane. Differential rotation gives
    // the inner plasma a faster flow rate than the outer edge.
    vec3 diskTangent = normalize(cross(diskNormal, vec3(1.0, 0.0, 0.0)));
    float angle = atan(dot(hit, diskTangent), hit.x);
    float orbitalSpeed = mix(1.8, 0.28, rn);
    float shear = angle + rn * 4.2;
    float broadFlow = fbm2(vec2(shear * 3.2, rn * 6.0 - time * orbitalSpeed));
    float filaments = fbm2(vec2(shear * 12.0 + time * 0.08, rn * 22.0));
    float fineGrain = fbm2(vec2(shear * 30.0 - time * 0.035, rn * 46.0));
    float turbulence = clamp(broadFlow * 0.52 + filaments * 0.33 + fineGrain * 0.15, 0.0, 1.0);
    float density = mix(0.18, 1.35, smoothstep(0.28, 0.76, turbulence));
    float hotFilament = smoothstep(0.55, 0.88, filaments) * (1.0 - rn);

    // A compact, hotter inner region with thin turbulent filaments instead
    // of a uniformly colored flat ring.
    diskCol += vec3(0.24, 0.09, 0.025) * hotFilament;

    // Relativistic Doppler beaming: the approaching side appears brighter.
    vec3 rayDir = normalize(b - a);
    vec3 tangentAtHit = normalize(cross(diskNormal, hit));
    float beam = dot(tangentAtHit, -rayDir);
    float beamFactor = pow(clamp(0.68 + beam * 0.78, 0.08, 2.0), 2.0);

    float innerCut = smoothstep(0.0, 0.025, rn);
    float outerCut = 1.0 - smoothstep(0.82, 1.0, rn);
    float edge = innerCut * outerCut;
    return (diskCol * density + vec3(0.12, 0.035, 0.008) * hotFilament)
      * beamFactor * edge * BLOOM_INTENSITY * 0.52;
  }

  vec3 traceRay(vec3 ro, vec3 rd, vec3 diskNormal) {
    float r0 = length(ro);
    float u = 1.0 / r0;
    vec3 normalVec = ro / r0;

    // The orbit plane is spanned by normalVec (radial at the camera) and
    // the component of the ray direction perpendicular to it — a photon's
    // path around a non-spinning hole always stays in this one plane.
    vec3 rdPerp = rd - normalVec * dot(rd, normalVec);
    float rdPerpLen = length(rdPerp);
    vec3 tangentVec;
    if (rdPerpLen > 1e-6) {
      tangentVec = rdPerp / rdPerpLen;
    } else {
      tangentVec = abs(normalVec.y) < 0.9
        ? normalize(cross(normalVec, vec3(0.0, 1.0, 0.0)))
        : normalize(cross(normalVec, vec3(1.0, 0.0, 0.0)));
    }

    // Initial du/dφ from the ray's radial vs. tangential direction cosines.
    float radialComp = dot(rd, normalVec);
    float tangComp = dot(rd, tangentVec);
    float du = (abs(tangComp) > 1e-6) ? -radialComp / tangComp * u : -sign(radialComp) * u * 200.0;
    du = clamp(du, -200.0, 200.0);

    float phi = 0.0;
    float baseStep = MAX_REVOLUTIONS * 6.28318530718 / float(RAY_STEPS);

    vec3 color = vec3(0.0);
    vec3 pos = ro;
    float minApproach = r0;
    bool captured = false;

    for (int i = 0; i < RAY_STEPS; i++) {
      // Finer angular steps near the photon sphere, where deflection is
      // sharpest and the disk/halo "joining" cusp actually forms.
      float photonProximity = exp(-14.0 * (u - 0.6667) * (u - 0.6667));
      float step = baseStep * (1.0 - 0.7 * photonProximity);

      vec3 oldPos = pos;
      integrateStep(u, du, step);
      phi += step;

      if (u >= 1.0 / HORIZON_R) {
        captured = true;
        break; // swallowed — whatever light was gathered en route, nothing more
      }

      // Avoid reconstructing a position at infinity if a coarse step reaches
      // the asymptotic escape region; dividing by a near-zero u causes NaNs.
      if (u <= 1.0 / 34.0) break;
      pos = (cos(phi) * normalVec + sin(phi) * tangentVec) / u;
      minApproach = min(minApproach, 1.0 / u);

      // Thin-disk intersection: did we cross the tilted equatorial plane?
      // pos is reconstructed as (...)/u, so as u shrinks toward the escape
      // threshold any tiny per-pixel difference upstream gets divided back
      // up into a large positional error — exactly the regime a ray is in
      // right after a strong deflection, on its way back out. That shows
      // up as speckle no smooth damping fixes without supersampling/TAA.
      // Fade the crossing test out smoothly as u drops toward that unsafe
      // range (a hard cutoff instead just traded speckle for a jagged
      // step edge, since the flip happens on a whole-step granularity).
      float uGate = smoothstep(1.1 / DISK_OUTER, 1.6 / DISK_OUTER, u);
      if (uGate > 0.0) {
        color += diskCrossingColor(oldPos, pos, diskNormal, uTime) * uGate;
      }

    }

    if (captured) return color;

    // Photon ring: a thin, bright rim wherever the path's closest approach
    // hugs the photon sphere. With a true geodesic this also naturally
    // catches higher-order lensed images that wind close to r = 1.5.
    float ringDist = abs(minApproach - PHOTON_R);
    // Gaussian falloffs avoid reversed smoothstep edges (undefined by GLSL)
    // and keep the photon ring narrow, smooth and high contrast.
    float ring = exp(-pow(ringDist / 0.055, 2.0))
               + 0.32 * exp(-pow(ringDist / 0.18, 2.0));
    color += vec3(0.95, 0.99, 1.0) * ring * BLOOM_INTENSITY;

    // Analytic exit direction from the Binet parametrisation — the exact
    // tangent to the geodesic where marching stopped — instead of a noisy
    // finite difference of the last two positions.
    vec3 rHat = cos(phi) * normalVec + sin(phi) * tangentVec;
    vec3 phiHat = -sin(phi) * normalVec + cos(phi) * tangentVec;
    vec3 exitDir = phiHat / max(u, 1e-4) - rHat * du / max(u * u, 1e-6);

    // Strongly-lensed rays (large total deflection) pack many stars into a
    // few pixels — genuine gravitational magnification, but at a finite
    // step budget without supersampling/TAA it aliases into speckle rather
    // than a clean smear. Fade the raw star sample out as deflection grows,
    // letting the smooth ring/disk glow (unaffected — it's geometry, not a
    // per-pixel noise sample) dominate that band instead.
    float deflection = 1.0 - dot(normalize(exitDir), rd);
    float lensDamp = smoothstep(0.15, 0.6, deflection);
    color += starField(normalize(exitDir)) * (1.0 - lensDamp);
    return color;
  }

  void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * uResolution) / uResolution.y;

    // Slow orbital drift — alive, never a spinning-logo kind of motion.
    float camDist = 23.0;
    float az = uTime * ROTATION_SPEED;
    // Kept low so the camera sits close to the disk's plane — near edge-on,
    // like the reference framing — rather than looking down on it face-on.
    float el = 0.14 + 0.03 * sin(uTime * 0.07);

    vec3 camPos = camDist * vec3(cos(el) * sin(az), sin(el), cos(el) * cos(az));
    vec3 forward = normalize(-camPos);
    vec3 worldUp = vec3(0.0, 1.0, 0.0);
    vec3 right = normalize(cross(forward, worldUp));
    vec3 up = cross(right, forward);

    float fov = 1.15;
    vec3 rd = normalize(forward + uv.x * fov * right + uv.y * fov * up);

    // The disk sits near the camera's orbital (X-Z) plane, tilted slightly
    // by INCLINATION, so the default framing is naturally near edge-on.
    vec3 diskNormal = normalize(vec3(0.0, cos(INCLINATION), sin(INCLINATION)));

    vec3 col = traceRay(camPos, rd, diskNormal);

    // Cheap Reinhard-ish tone mapping so bright highlights glow without
    // hard-clipping to white.
    col = col / (col + vec3(1.0));
    col = pow(col, vec3(1.3));

    gl_FragColor = vec4(col, 1.0);
  }
`

function compileShader(gl, type, source) {
  const shader = gl.createShader(type)
  gl.shaderSource(shader, source)
  gl.compileShader(shader)
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const info = gl.getShaderInfoLog(shader)
    gl.deleteShader(shader)
    throw new Error(`Shader compile error: ${info}`)
  }
  return shader
}

function createProgram(gl, vertexSource, fragmentSource) {
  const vertexShader = compileShader(gl, gl.VERTEX_SHADER, vertexSource)
  const fragmentShader = compileShader(gl, gl.FRAGMENT_SHADER, fragmentSource)
  const program = gl.createProgram()
  gl.attachShader(program, vertexShader)
  gl.attachShader(program, fragmentShader)
  gl.linkProgram(program)
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const info = gl.getProgramInfoLog(program)
    gl.deleteProgram(program)
    throw new Error(`Program link error: ${info}`)
  }
  gl.deleteShader(vertexShader)
  gl.deleteShader(fragmentShader)
  return program
}

// Internal render resolution is capped and upscaled via CSS — raymarching
// every screen pixel at full device resolution is the single biggest cost
// lever here, so this is the one that keeps it off a laptop GPU's knees.
const MAX_INTERNAL_LONG_EDGE = 1280

export default function BlackHole({ className = '', style }) {
  const canvasRef = useRef(null)
  const [supported, setSupported] = useState(true)
  const reducedMotion = usePrefersReducedMotion()

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return undefined

    const gl =
      canvas.getContext('webgl', { antialias: false, alpha: false, powerPreference: 'high-performance' }) ||
      canvas.getContext('experimental-webgl')

    if (!gl) {
      setSupported(false)
      return undefined
    }

    let program
    try {
      program = createProgram(gl, VERTEX_SHADER, FRAGMENT_SHADER)
    } catch (err) {
      console.error('[BlackHole] shader setup failed:', err)
      setSupported(false)
      return undefined
    }

    const positionBuffer = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer)
    // One oversized triangle covering the whole clip space — cheaper than a quad.
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)

    const aPosition = gl.getAttribLocation(program, 'aPosition')
    const uResolution = gl.getUniformLocation(program, 'uResolution')
    const uTime = gl.getUniformLocation(program, 'uTime')

    gl.enableVertexAttribArray(aPosition)
    gl.vertexAttribPointer(aPosition, 2, gl.FLOAT, false, 0, 0)

    let width = 0
    let height = 0
    let rafId = null
    let disposed = false
    let pageVisible = !document.hidden
    const startTime = performance.now()

    const drawFrame = (now) => {
      if (disposed || gl.isContextLost()) return
      const elapsed = reducedMotion ? 0 : (now - startTime) / 1000
      gl.useProgram(program)
      gl.uniform2f(uResolution, width, height)
      gl.uniform1f(uTime, elapsed)
      gl.drawArrays(gl.TRIANGLES, 0, 3)
    }

    const tick = (now) => {
      rafId = null
      if (disposed || !pageVisible) return
      drawFrame(now)
      if (!reducedMotion) rafId = requestAnimationFrame(tick)
    }

    const scheduleRender = () => {
      if (disposed || !pageVisible) return
      if (reducedMotion) {
        drawFrame(performance.now())
      } else if (rafId === null) {
        rafId = requestAnimationFrame(tick)
      }
    }

    const resize = () => {
      const parent = canvas.parentElement
      const cssWidth = parent ? parent.clientWidth : window.innerWidth
      const cssHeight = parent ? parent.clientHeight : window.innerHeight
      const longEdge = Math.max(cssWidth, cssHeight, 1)
      const scale = Math.min(1, MAX_INTERNAL_LONG_EDGE / longEdge)
      const nextWidth = Math.max(1, Math.round(cssWidth * scale))
      const nextHeight = Math.max(1, Math.round(cssHeight * scale))
      if (canvas.width !== nextWidth || canvas.height !== nextHeight) {
        width = nextWidth
        height = nextHeight
        canvas.width = width
        canvas.height = height
        gl.viewport(0, 0, width, height)
      }
      scheduleRender()
    }

    const onVisibilityChange = () => {
      pageVisible = !document.hidden
      if (!pageVisible && rafId !== null) {
        cancelAnimationFrame(rafId)
        rafId = null
      } else {
        scheduleRender()
      }
    }

    const onContextLost = (event) => {
      event.preventDefault()
      disposed = true
      if (rafId !== null) cancelAnimationFrame(rafId)
      rafId = null
      setSupported(false)
    }

    resize()
    let resizeObserver = null
    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(resize)
      if (canvas.parentElement) resizeObserver.observe(canvas.parentElement)
    }
    window.addEventListener('resize', resize, { passive: true })
    document.addEventListener('visibilitychange', onVisibilityChange)
    canvas.addEventListener('webglcontextlost', onContextLost, false)
    scheduleRender()

    return () => {
      disposed = true
      if (rafId !== null) cancelAnimationFrame(rafId)
      window.removeEventListener('resize', resize)
      document.removeEventListener('visibilitychange', onVisibilityChange)
      canvas.removeEventListener('webglcontextlost', onContextLost, false)
      if (resizeObserver) resizeObserver.disconnect()
      gl.deleteBuffer(positionBuffer)
      gl.deleteProgram(program)
      // Keep the canvas context alive between React effect cleanups. Explicitly
      // losing it here breaks StrictMode re-mounts and preference changes.
  }, [reducedMotion])

  if (!supported) {
    return (
      <div
        className={className}
        style={{
          background:
            'radial-gradient(circle at 55% 45%, rgba(186,248,255,0.35) 0%, rgba(34,211,238,0.12) 30%, #030607 62%)',
          ...style,
        }}
        aria-hidden="true"
      />
    )
  }

  return (
    <canvas
      ref={canvasRef}
      className={className}
      style={{ display: 'block', width: '100%', height: '100%', ...style }}
      aria-hidden="true"
    />
  )
}
