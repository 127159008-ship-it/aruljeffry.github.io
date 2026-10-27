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
  const float INCLINATION      = 0.16;  // small angle above the disk plane: near edge-on
  const float DISK_ROLL        = 0.35;  // rotate the full lensing view ~20 degrees
  const float SCREEN_TO_WORLD  = 19.0;  // fits the full lensed disk inside the viewport
  const float CAMERA_DISTANCE  = 16.0;  // fixed distant camera: no fake camera orbit or scroll zoom
  const float DISK_INNER       = 1.9;   // inner edge of the luminous plasma
  const float DISK_OUTER       = 8.0;   // outer radius of the disk
  const float DISK_GAIN        = 2.4;   // disk emission
  const float DISK_OPACITY     = 0.20;  // low opacity lets multiple lensed disk images remain visible
  const float DISK_SPEED       = 1.15;  // slow plasma pattern motion
  const float DISK_WIND        = 5.7;   // spiral filament winding
  const float DISK_CONTRAST    = 1.35;  // visible filaments without black bands
  const float DOPPLER_MIX      = 0.23;  // subtle relativistic asymmetry; don't blacken the far side
  const float EXPOSURE         = 1.20;  // final glow exposure
  const float HORIZON_R        = 1.0;   // Schwarzschild event-horizon radius
  const vec3  DISK_HOT         = vec3(0.73, 0.97, 1.00); // ice-cyan highlight: #baf8ff
  const vec3  DISK_COOL        = vec3(0.10, 0.61, 0.72); // outer plasma: saturated theme cyan
  const int   RAY_STEPS        = 64;    // adaptive 3D ray integration steps
  // ---------------------------------------------------------------------

  float hash21(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
  }

  // Periodic value-noise field. Wrapping the angular coordinate avoids a
  // visible seam where the disk texture crosses the atan() branch cut.
  float vnoiseWrapY(vec2 p, float period) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float y0 = mod(i.y, period);
    float y1 = mod(i.y + 1.0, period);
    float a = hash21(vec2(i.x, y0));
    float b = hash21(vec2(i.x + 1.0, y0));
    float c = hash21(vec2(i.x, y1));
    float d = hash21(vec2(i.x + 1.0, y1));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
  }

  // 3D Schwarzschild photon tracing. Unlike a painted ring or a screen-space
  // ellipse, every pixel follows its own curved ray. A ray may cross the
  // accretion disk several times, so the far side is naturally lensed above
  // and below the black shadow. The adaptive leapfrog trace follows the
  // approach used by the MIT-licensed s13k/ghostty-blackhole shader; see
  // THIRD_PARTY_NOTICES.md for attribution and license.
  vec3 traceRay(vec3 x, vec3 initialV, float time) {
    vec3 v = initialV;
    float h2 = dot(cross(x, v), cross(x, v));

    // Disk plane is almost edge-on to the fixed camera. e2 is the second
    // in-plane basis vector, used for seamless angular streak coordinates.
    vec3 n = normalize(vec3(0.0, cos(INCLINATION), sin(INCLINATION)));
    vec3 e2 = vec3(0.0, -sin(INCLINATION), cos(INCLINATION));

    vec3 emitted = vec3(0.0);
    float transmittance = 1.0;
    float previousSide = dot(x, n);
    vec3 previousPosition = x;

    for (int i = 0; i < RAY_STEPS; i++) {
      float r2 = dot(x, x);
      if (r2 < HORIZON_R * HORIZON_R) break;
      if (x.z < -CAMERA_DISTANCE && v.z < 0.0) break;
      if (r2 > 4.0 * CAMERA_DISTANCE * CAMERA_DISTANCE) break;

      float r = sqrt(r2);
      // Adaptive step length: finer in the strongly curved region, cheaper
      // in the weak-field region far from the event horizon.
      float dt = clamp(0.16 * r, 0.03, 1.5);
      vec3 acceleration = -1.5 * h2 * x / (r2 * r2 * r);
      v += acceleration * (0.5 * dt);
      x += v * dt;

      // The drift can cross the horizon in a single adaptive step. Stop
      // before evaluating the singular force inside r = 1, avoiding NaNs
      // or bright speckles at the silhouette edge.
      r2 = dot(x, x);
      if (r2 < HORIZON_R * HORIZON_R) break;
      r = sqrt(r2);
      acceleration = -1.5 * h2 * x / (r2 * r2 * r);
      v += acceleration * (0.5 * dt);

      // The curved ray pierced the thin disk plane; interpolate the crossing
      // for a clean hit point instead of sampling a whole integration step.
      float side = dot(x, n);
      if (side * previousSide < 0.0 && transmittance > 0.015) {
        float crossingT = previousSide / (previousSide - side);
        vec3 hit = mix(previousPosition, x, crossingT);
        float radius = length(hit);

        if (radius > DISK_INNER && radius < DISK_OUTER) {
          float band = smoothstep(DISK_INNER, DISK_INNER * 1.22, radius)
                     * (1.0 - smoothstep(DISK_OUTER * 0.72, DISK_OUTER, radius));

          float phi = atan(dot(hit, e2), hit.x);
          float turns = phi / 6.2831853;
          float kep = pow(DISK_INNER / radius, 1.5);
          float gravitationalShift = sqrt(max(1.0 - 1.5 / radius, 0.02));
          float swirl = radius * DISK_WIND * 0.12
                      - time * kep * DISK_SPEED * gravitationalShift;

          float streaks =
              vnoiseWrapY(vec2(radius * 2.8, turns * 19.0 + swirl * 3.0), 19.0) * 0.65
            + vnoiseWrapY(vec2(radius * 1.0, turns * 9.0 + swirl * 1.5 + 7.0), 9.0) * 0.35;
          streaks = 0.42 + DISK_CONTRAST * streaks * streaks;

          // A restrained relativistic brightness shift adds depth without
          // allowing the receding/far side to collapse into a black stripe.
          vec3 gasDirection = normalize(cross(n, hit));
          float beta = clamp(inversesqrt(max(2.0 * (radius - 1.0), 0.2)), 0.0, 0.72);
          float gRaw = gravitationalShift
                     / max(1.0 + beta * dot(gasDirection, normalize(v)), 0.10);
          float g = mix(1.0, gRaw, DOPPLER_MIX);
          float boost = pow(clamp(g, 0.80, 1.24), 1.35);

          // Shakura–Sunyaev radial temperature profile, remapped only into the
          // portfolio's cyan palette. The center remains black; the inner
          // disk is icy cyan-white and the outer disk keeps a richer teal tone.
          float xpr = max(1.0 - sqrt(DISK_INNER / radius), 0.0);
          float temperatureProfile =
            pow(DISK_INNER / radius, 0.75) * pow(xpr, 0.25) / 0.488;
          float hotness = clamp(pow(max(temperatureProfile, 0.0), 0.45), 0.0, 1.0);
          vec3 diskColor = mix(DISK_COOL, DISK_HOT, hotness);

          float density = band * streaks;
          float emissivity = DISK_GAIN * density
                           * pow(max(temperatureProfile, 0.0), 1.65) * boost;
          emitted += transmittance * diskColor * emissivity;

          // Modest absorption allows the far-side disk to shine through each
          // nearer crossing, giving the layered, lensed arcs in the reference.
          transmittance *= 1.0 - clamp(DISK_OPACITY * density, 0.0, 0.48);
        }
      }

      previousSide = side;
      previousPosition = x;
    }

    // The surrounding background is deliberately black; the luminous rings
    // arise from the ray crossing the disk at different lensed image orders.
    return emitted;
  }

  void main() {
    // Pixel coordinates are mapped to a fixed impact-parameter plane. The
    // viewpoint does not orbit or zoom; only the plasma pattern evolves.
    vec2 uv = (gl_FragCoord.xy - 0.5 * uResolution) / uResolution.y;
    float rollCos = cos(DISK_ROLL);
    float rollSin = sin(DISK_ROLL);
    vec2 rolledUv = vec2(
      rollCos * uv.x - rollSin * uv.y,
      rollSin * uv.x + rollCos * uv.y
    );

    vec2 impact = rolledUv * SCREEN_TO_WORLD;
    vec3 cameraPosition = vec3(impact, CAMERA_DISTANCE);
    vec3 rayDirection = vec3(0.0, 0.0, -1.0);
    vec3 emission = traceRay(cameraPosition, rayDirection, uTime);

    // Exponential tone mapping and display gamma keep luminous areas bright
    // while preserving cyan saturation and the truly black event horizon.
    vec3 col = 1.0 - exp(-emission * EXPOSURE);
    col = pow(clamp(col, 0.0, 1.0), vec3(0.72));

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
    let inViewport = true
    let startTime = performance.now()
    let pauseStarted = pageVisible ? null : startTime

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
      if (disposed || !pageVisible || !inViewport) return
      drawFrame(now)
      if (!reducedMotion) rafId = requestAnimationFrame(tick)
    }

    const scheduleRender = () => {
      if (disposed || !pageVisible || !inViewport) return
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

    const syncActivity = () => {
      const now = performance.now()
      const active = pageVisible && inViewport
      if (!active) {
        if (pauseStarted === null) pauseStarted = now
        if (rafId !== null) cancelAnimationFrame(rafId)
        rafId = null
        return
      }

      // Freeze shader time whenever the page is hidden or the hero scrolls
      // out of view, so it resumes smoothly without wasting GPU time.
      if (pauseStarted !== null) {
        startTime += now - pauseStarted
        pauseStarted = null
      }
      scheduleRender()
    }

    const onVisibilityChange = () => {
      pageVisible = !document.hidden
      syncActivity()
    }

    const onIntersectionChange = (entries) => {
      inViewport = entries.some((entry) => entry.isIntersecting)
      syncActivity()
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
    let intersectionObserver = null
    if (typeof IntersectionObserver !== 'undefined') {
      intersectionObserver = new IntersectionObserver(onIntersectionChange, { rootMargin: '100px' })
      intersectionObserver.observe(canvas.parentElement || canvas)
    }
    window.addEventListener('resize', resize, { passive: true })
    document.addEventListener('visibilitychange', onVisibilityChange)
    canvas.addEventListener('webglcontextlost', onContextLost, false)
    syncActivity()

    return () => {
      disposed = true
      if (rafId !== null) cancelAnimationFrame(rafId)
      window.removeEventListener('resize', resize)
      document.removeEventListener('visibilitychange', onVisibilityChange)
      canvas.removeEventListener('webglcontextlost', onContextLost, false)
      if (resizeObserver) resizeObserver.disconnect()
      if (intersectionObserver) intersectionObserver.disconnect()
      gl.deleteBuffer(positionBuffer)
      gl.deleteProgram(program)
      // Keep the canvas context alive between React effect cleanups. Explicitly
      // losing it here breaks StrictMode re-mounts and preference changes.
    }
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
