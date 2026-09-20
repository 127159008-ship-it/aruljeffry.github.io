import { useEffect, useRef, useState } from 'react'
import usePrefersReducedMotion from './usePrefersReducedMotion'

const VERTEX_SHADER = `
  attribute vec2 aPosition;
  void main() {
    gl_Position = vec4(aPosition, 0.0, 1.0);
  }
`

// A raymarched approximation of Schwarzschild lensing: rays are bent toward
// the singularity by an inverse-square-ish curvature term each step instead
// of solving the full geodesic ODE. Close enough to sell the illusion —
// stars smear into arcs near the shadow, and the same ray can cross the
// accretion disk plane twice (direct image + bent "wrapped" image) for
// free, since the ray is genuinely marched through curved space rather
// than faked with a second flat ring mesh.
const FRAGMENT_SHADER = `
  precision highp float;

  uniform vec2 uResolution;
  uniform float uTime;

  // ---------------------------------------------------------------------
  // Tunables — adjust the look here without touching the logic below.
  // ---------------------------------------------------------------------
  const float LENS_STRENGTH   = 2.6;    // gravitational bending strength
  const float INCLINATION     = 0.34;   // disk tilt off edge-on, radians
  const float ROTATION_SPEED  = 0.045;  // camera drift speed
  const float DISK_INNER      = 2.6;    // inner radius, in horizon radii (~ISCO)
  const float DISK_OUTER      = 9.0;    // outer radius, in horizon radii
  const float BLOOM_INTENSITY = 1.6;
  const float HORIZON_R       = 1.0;    // event horizon radius
  const float PHOTON_R        = 1.5;    // photon sphere radius -> the bright ring
  const vec3  DISK_HOT        = vec3(0.85, 0.97, 1.0);  // near-ISCO: blue-white
  const vec3  DISK_COOL       = vec3(1.0, 0.55, 0.22);  // outer edge: orange-red
  const int   RAY_STEPS       = 90;
  // ---------------------------------------------------------------------

  float hash21(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
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
      star = smoothstep(size, 0.0, d) * mix(0.35, 1.0, hash21(cell + 9.0));
    }
    vec3 tint = mix(vec3(0.75, 0.85, 1.0), vec3(1.0, 0.92, 0.82), hash21(cell + 13.0));
    return vec3(star) * tint;
  }

  vec3 traceRay(vec3 ro, vec3 rd, vec3 diskNormal) {
    vec3 pos = ro;
    vec3 dir = rd;
    vec3 color = vec3(0.0);
    float minApproach = 1000.0;
    float stepSize = 0.15;

    for (int i = 0; i < RAY_STEPS; i++) {
      float r = length(pos);
      minApproach = min(minApproach, r);

      if (r < HORIZON_R) {
        return color; // swallowed — whatever light was gathered en route, nothing more
      }

      // Curvature: bend the ray toward the singularity, stronger up close.
      vec3 toCenter = -pos;
      float bend = LENS_STRENGTH / (r * r * r);
      dir = normalize(dir + toCenter * bend * stepSize);

      // Finer steps near the hole (where curvature is sharp), coarser far out.
      stepSize = clamp(r * 0.10, 0.02, 0.35);
      vec3 next = pos + dir * stepSize;

      // Thin-disk intersection: did we cross the tilted equatorial plane?
      float d0 = dot(pos, diskNormal);
      float d1 = dot(next, diskNormal);
      if (d0 * d1 < 0.0) {
        float t = d0 / (d0 - d1);
        vec3 hit = mix(pos, next, t);
        float rad = length(hit);
        if (rad > DISK_INNER && rad < DISK_OUTER) {
          float rn = clamp((rad - DISK_INNER) / (DISK_OUTER - DISK_INNER), 0.0, 1.0);
          vec3 diskCol = mix(DISK_HOT, DISK_COOL, rn);

          // Relativistic beaming: brighter where the disk's orbital motion
          // points toward the camera, dimmer on the receding side.
          vec3 tangent = normalize(cross(diskNormal, hit));
          float beam = dot(tangent, -dir);
          float beamFactor = pow(clamp(0.65 + beam, 0.0, 2.2), 2.0);

          float density = 1.0 - smoothstep(DISK_OUTER * 0.75, DISK_OUTER, rad);
          color += diskCol * beamFactor * density * BLOOM_INTENSITY * 0.35;
        }
      }

      pos = next;
      if (r > 30.0) break; // escaped to the background
    }

    // Photon ring: a bright rim wherever a ray's closest approach hugs the
    // photon sphere — the signature "ring" silhouette, brighter than the disk.
    float ring = smoothstep(0.35, 0.0, abs(minApproach - PHOTON_R));
    color += vec3(0.92, 0.99, 1.0) * ring * BLOOM_INTENSITY;

    color += starField(dir);
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
    col = pow(col, vec3(0.85));

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
const MAX_INTERNAL_LONG_EDGE = 1100

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

    const resize = () => {
      const parent = canvas.parentElement
      const cssWidth = parent ? parent.clientWidth : window.innerWidth
      const cssHeight = parent ? parent.clientHeight : window.innerHeight
      const longEdge = Math.max(cssWidth, cssHeight, 1)
      const scale = Math.min(1, MAX_INTERNAL_LONG_EDGE / longEdge)
      width = Math.max(1, Math.round(cssWidth * scale))
      height = Math.max(1, Math.round(cssHeight * scale))
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width
        canvas.height = height
        gl.viewport(0, 0, width, height)
      }
    }

    resize()
    const resizeObserver = new ResizeObserver(resize)
    if (canvas.parentElement) resizeObserver.observe(canvas.parentElement)
    window.addEventListener('resize', resize)

    let rafId = null
    const startTime = performance.now()

    const render = (now) => {
      const elapsed = reducedMotion ? 0 : (now - startTime) / 1000

      gl.useProgram(program)
      gl.uniform2f(uResolution, width, height)
      gl.uniform1f(uTime, elapsed)
      gl.drawArrays(gl.TRIANGLES, 0, 3)

      if (!reducedMotion) {
        rafId = requestAnimationFrame(render)
      }
    }

    rafId = requestAnimationFrame(render)

    return () => {
      if (rafId) cancelAnimationFrame(rafId)
      window.removeEventListener('resize', resize)
      resizeObserver.disconnect()
      gl.deleteBuffer(positionBuffer)
      gl.deleteProgram(program)
      const loseContext = gl.getExtension('WEBGL_lose_context')
      if (loseContext) loseContext.loseContext()
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
