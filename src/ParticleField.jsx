import { useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { EffectComposer, Bloom } from '@react-three/postprocessing'
import * as THREE from 'three'
import usePrefersReducedMotion from './usePrefersReducedMotion'

// Tunables — kept in one place so the feel of the scene can be adjusted
// without hunting through the render/physics code below.
const CONFIG = {
  dust: { desktop: 190, tablet: 120, mobile: 60 },
  mid: { desktop: 100, tablet: 64, mobile: 36 },
  near: { desktop: 56, tablet: 36, mobile: 20 },
  midConnections: 2,
  nearConnections: 3,
  twinkleChance: 0.0025,
  cursorRadius: 2.4,
  cursorStrength: 0.9,
  scrollTravel: 20,
  debrisSlots: 4,
  debrisMinDelay: 9,
  debrisMaxDelay: 24,
  debrisDuration: [4.5, 7],
  crystals: { desktop: 32, tablet: 20, mobile: 10 },
  stars: { desktop: 280, tablet: 170, mobile: 80 },
  sparkles: { desktop: 12, tablet: 7, mobile: 3 },
  shootingStars: { desktop: 7, tablet: 5, mobile: 3 },
}

const BLACK_HOLE = {
  x: 13.5,
  y: 1.8,
  z: -23,
  horizonRadius: 2.4,
  pullRadius: 11,
  gravityStrength: 0.017,
}

function useScrollProgressRef() {
  const ref = useRef(0)
  useEffect(() => {
    const onScroll = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight
      ref.current = max > 0 ? Math.min(window.scrollY / max, 1) : 0
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])
  return ref
}

const GLOW_VERTEX_SHADER = `
  attribute float aSize;
  uniform float uScale;
  void main() {
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = aSize * uScale * (300.0 / -mvPosition.z);
    gl_Position = projectionMatrix * mvPosition;
  }
`

const GLOW_FRAGMENT_SHADER = `
  uniform sampler2D uMap;
  uniform vec3 uColor;
  uniform float uOpacity;
  void main() {
    vec4 tex = texture2D(uMap, gl_PointCoord);
    gl_FragColor = vec4(uColor, tex.a * uOpacity);
  }
`

function GlowPointsMaterial({ map, color, opacity, scale }) {
  const uniforms = useMemo(
    () => ({
      uMap: { value: map },
      uColor: { value: new THREE.Color(color) },
      uOpacity: { value: opacity },
      uScale: { value: scale },
    }),
    [map, color, opacity, scale]
  )
  return (
    <shaderMaterial
      transparent
      depthWrite={false}
      blending={THREE.AdditiveBlending}
      uniforms={uniforms}
      vertexShader={GLOW_VERTEX_SHADER}
      fragmentShader={GLOW_FRAGMENT_SHADER}
    />
  )
}

function useGlowTexture() {
  return useMemo(() => {
    const size = 64
    const canvas = document.createElement('canvas')
    canvas.width = size
    canvas.height = size
    const ctx = canvas.getContext('2d')
    const gradient = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
    gradient.addColorStop(0, 'rgba(255,255,255,1)')
    gradient.addColorStop(0.4, 'rgba(255,255,255,0.55)')
    gradient.addColorStop(1, 'rgba(255,255,255,0)')
    ctx.fillStyle = gradient
    ctx.fillRect(0, 0, size, size)
    const texture = new THREE.CanvasTexture(canvas)
    texture.needsUpdate = true
    return texture
  }, [])
}

// A tiny four-point diffraction-spike sprite — the classic "glint" shape a
// bright star makes through a camera lens or the human eye, used for the
// handful of standout glitter particles rather than the soft round glow.
function useSparkleTexture() {
  return useMemo(() => {
    const size = 128
    const c = size / 2
    const canvas = document.createElement('canvas')
    canvas.width = size
    canvas.height = size
    const ctx = canvas.getContext('2d')

    const core = ctx.createRadialGradient(c, c, 0, c, c, size * 0.17)
    core.addColorStop(0, 'rgba(255,255,255,1)')
    core.addColorStop(1, 'rgba(255,255,255,0)')
    ctx.fillStyle = core
    ctx.fillRect(0, 0, size, size)

    const drawSpike = (w, h) => {
      const grad = ctx.createLinearGradient(0, -h, 0, h)
      grad.addColorStop(0, 'rgba(255,255,255,0)')
      grad.addColorStop(0.5, 'rgba(255,255,255,0.9)')
      grad.addColorStop(1, 'rgba(255,255,255,0)')
      ctx.fillStyle = grad
      ctx.fillRect(-w / 2, -h, w, h * 2)
    }
    ctx.save()
    ctx.translate(c, c)
    drawSpike(size * 0.045, size * 0.5)
    ctx.rotate(Math.PI / 2)
    drawSpike(size * 0.045, size * 0.5)
    ctx.restore()

    const texture = new THREE.CanvasTexture(canvas)
    texture.needsUpdate = true
    return texture
  }, [])
}

// Realistic star tints — mostly white/blue-white with a scattering of
// warmer stars, roughly matching how a real night sky reads to the eye.
function pickStarColor() {
  const r = Math.random()
  if (r < 0.5) return [1, 1, 1]
  if (r < 0.78) return [0.74, 0.85, 1]
  if (r < 0.94) return [1, 0.93, 0.8]
  return [1, 0.8, 0.64]
}

const STAR_VERTEX_SHADER = `
  attribute float aSize;
  attribute vec3 aColor;
  uniform float uScale;
  varying vec3 vColor;
  void main() {
    vColor = aColor;
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = aSize * uScale * (300.0 / -mvPosition.z);
    gl_Position = projectionMatrix * mvPosition;
  }
`

const STAR_FRAGMENT_SHADER = `
  uniform sampler2D uMap;
  uniform float uOpacity;
  varying vec3 vColor;
  void main() {
    vec4 tex = texture2D(uMap, gl_PointCoord);
    gl_FragColor = vec4(vColor, tex.a * uOpacity);
  }
`

function StarPointsMaterial({ map, opacity, scale }) {
  const uniforms = useMemo(
    () => ({
      uMap: { value: map },
      uOpacity: { value: opacity },
      uScale: { value: scale },
    }),
    [map, opacity, scale]
  )
  return (
    <shaderMaterial
      transparent
      depthWrite={false}
      blending={THREE.AdditiveBlending}
      uniforms={uniforms}
      vertexShader={STAR_VERTEX_SHADER}
      fragmentShader={STAR_FRAGMENT_SHADER}
    />
  )
}

// A wide, deep field of tiny twinkling stars scattered evenly across the
// whole backdrop (unlike the clustered nebula/network layers), each with
// its own colour, phase and twinkle speed for a natural scintillation feel.
function StarField({ count, glowTexture, reduced }) {
  const pointsRef = useRef()

  const stars = useMemo(() => {
    const arr = []
    for (let i = 0; i < count; i++) {
      const isBright = Math.random() > 0.9
      const [r, g, b] = pickStarColor()
      arr.push({
        x: (Math.random() - 0.5) * 180,
        y: (Math.random() - 0.5) * 96,
        z: -30 - Math.random() * 55,
        size: isBright ? 0.6 + Math.random() * 0.6 : 0.15 + Math.random() * 0.22,
        phase: Math.random() * Math.PI * 2,
        speed: 0.5 + Math.random() * 1.7,
        flare: 0,
        flareChance: isBright ? 0.012 : 0.0022,
        r, g, b,
      })
    }
    return arr
  }, [count])

  const positions = useMemo(() => {
    const arr = new Float32Array(stars.length * 3)
    stars.forEach((s, i) => {
      arr[i * 3] = s.x
      arr[i * 3 + 1] = s.y
      arr[i * 3 + 2] = s.z
    })
    return arr
  }, [stars])
  const colors = useMemo(() => {
    const arr = new Float32Array(stars.length * 3)
    stars.forEach((s, i) => {
      arr[i * 3] = s.r
      arr[i * 3 + 1] = s.g
      arr[i * 3 + 2] = s.b
    })
    return arr
  }, [stars])
  const sizes = useMemo(() => new Float32Array(stars.length), [stars])

  useFrame((state, delta) => {
    const geo = pointsRef.current?.geometry
    if (!geo) return
    const sizeAttr = geo.attributes.aSize
    for (let i = 0; i < stars.length; i++) {
      const s = stars[i]
      if (!reduced) {
        s.phase += delta * s.speed
        if (Math.random() < s.flareChance) s.flare = 1
        s.flare *= 0.9
      }
      const twinkle = 0.5 + Math.sin(s.phase) * 0.35 + s.flare * 2.4
      sizeAttr.array[i] = s.size * Math.max(twinkle, 0.1)
    }
    sizeAttr.needsUpdate = true
  })

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" count={stars.length} array={positions} itemSize={3} />
        <bufferAttribute attach="attributes-aSize" count={stars.length} array={sizes} itemSize={1} />
        <bufferAttribute attach="attributes-aColor" count={stars.length} array={colors} itemSize={3} />
      </bufferGeometry>
      <StarPointsMaterial map={glowTexture} opacity={0.9} scale={0.5} />
    </points>
  )
}

// A small handful of brighter, closer "glitter" stars that flash with a
// four-point diffraction spike — the sparkle accents the sea of tiny
// background stars alone can't give.
function SparkleField({ count, sparkleTexture, reduced }) {
  const items = useMemo(() => {
    const arr = []
    for (let i = 0; i < count; i++) {
      arr.push({
        x: (Math.random() - 0.5) * 50,
        y: (Math.random() - 0.5) * 28,
        z: -4 - Math.random() * 30,
        baseScale: 0.4 + Math.random() * 0.55,
        phase: Math.random() * Math.PI * 2,
        speed: 0.5 + Math.random() * 1.1,
        flare: 0,
        rot: Math.random() * Math.PI,
      })
    }
    return arr
  }, [count])
  const refs = useRef([])

  useFrame((state, delta) => {
    items.forEach((it, i) => {
      const mesh = refs.current[i]
      if (!mesh) return
      if (!reduced) {
        it.phase += delta * it.speed
        if (Math.random() < 0.01) it.flare = 1
        it.flare *= 0.92
        it.rot += delta * 0.12
      }
      const twinkle = 0.35 + Math.sin(it.phase) * 0.3 + it.flare * 1.9
      const s = it.baseScale * Math.max(twinkle, 0.18)
      mesh.scale.set(s, s, 1)
      mesh.material.rotation = it.rot
      mesh.material.opacity = Math.min(0.3 + twinkle * 0.45, 1)
    })
  })

  return (
    <group>
      {items.map((it, i) => (
        <sprite key={i} ref={(el) => (refs.current[i] = el)} position={[it.x, it.y, it.z]}>
          <spriteMaterial
            map={sparkleTexture}
            color="#eafcff"
            transparent
            opacity={0.6}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
          />
        </sprite>
      ))}
    </group>
  )
}

function clusteredField(count, { zMin, zMax, spread, clusterCount = 5, clusterRatio = 0.6 }) {
  const clusters = new Array(clusterCount).fill(null).map(() => ({
    x: (Math.random() - 0.5) * spread * 1.4,
    y: (Math.random() - 0.5) * spread * 0.9,
  }))
  const points = []
  for (let i = 0; i < count; i++) {
    const z = zMin + Math.random() * (zMax - zMin)
    let x, y
    if (Math.random() < clusterRatio) {
      const c = clusters[Math.floor(Math.random() * clusters.length)]
      x = c.x + (Math.random() - 0.5) * spread * 0.35
      y = c.y + (Math.random() - 0.5) * spread * 0.35
    } else {
      x = (Math.random() - 0.5) * spread * 1.6
      y = (Math.random() - 0.5) * spread * 1.1
    }
    points.push({
      baseX: x,
      baseY: y,
      x, y, z,
      phase: Math.random() * Math.PI * 2,
      speed: 0.15 + Math.random() * 0.25,
      amp: 0.06 + Math.random() * 0.1,
      size: 0.3 + Math.random() * 0.42,
      flare: 0,
      gx: 0,
      gy: 0,
      gz: 0,
    })
  }
  return points
}

function buildLayerEdges(points, k) {
  const edgeSet = new Set()
  const edges = []
  points.forEach((p, i) => {
    const distances = points
      .map((o, j) => (i === j ? null : { j, d: (p.x - o.x) ** 2 + (p.y - o.y) ** 2 + (p.z - o.z) ** 2 }))
      .filter(Boolean)
      .sort((a, b) => a.d - b.d)
      .slice(0, k)
    distances.forEach(({ j }) => {
      const key = i < j ? `${i}-${j}` : `${j}-${i}`
      if (!edgeSet.has(key)) {
        edgeSet.add(key)
        edges.push([i, j])
      }
    })
  })
  return edges
}

function buildAdjacency(pointCount, edges) {
  const adjacency = Array.from({ length: pointCount }, () => [])
  edges.forEach(([a, b]) => {
    adjacency[a].push(b)
    adjacency[b].push(a)
  })
  return adjacency
}

function DustLayer({ count, glowTexture, reduced }) {
  const pointsRef = useRef()
  const { camera } = useThree()
  const points = useMemo(
    () => clusteredField(count, { zMin: -70, zMax: -15, spread: 46, clusterCount: 6, clusterRatio: 0.5 }),
    [count]
  )
  const positions = useMemo(() => new Float32Array(points.length * 3), [points])
  const sizes = useMemo(() => new Float32Array(points.length), [points])

  useFrame((state, delta) => {
    const geo = pointsRef.current?.geometry
    if (!geo) return
    const posAttr = geo.attributes.position
    const sizeAttr = geo.attributes.aSize

    for (let i = 0; i < points.length; i++) {
      const p = points[i]
      if (!reduced) {
        p.phase += delta * p.speed
        if (p.z > camera.position.z + 4) {
          p.z = camera.position.z - 60 - Math.random() * 15
          p.baseX = (Math.random() - 0.5) * 46
          p.baseY = (Math.random() - 0.5) * 30
          p.x = p.baseX
          p.y = p.baseY
        }
        if (Math.random() < CONFIG.twinkleChance) p.flare = 1
        p.flare *= 0.94
      }
      const tw = 0.7 + Math.sin(p.phase) * 0.3 + p.flare * 1.4
      posAttr.array[i * 3] = p.x
      posAttr.array[i * 3 + 1] = p.y
      posAttr.array[i * 3 + 2] = p.z
      sizeAttr.array[i] = p.size * tw
    }
    posAttr.needsUpdate = true
    sizeAttr.needsUpdate = true
  })

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" count={points.length} array={positions} itemSize={3} />
        <bufferAttribute attach="attributes-aSize" count={points.length} array={sizes} itemSize={1} />
      </bufferGeometry>
      <GlowPointsMaterial map={glowTexture} color="#dfeef2" opacity={0.6} scale={0.38} />
    </points>
  )
}

function NetworkLayer({ count, zMin, zMax, spread, k, glowTexture, cursorReactive, reduced, colorCore, colorLine, opacityLine, gravity }) {
  const pointsRef = useRef()
  const lineRef = useRef()
  const { camera, size } = useThree()
  const mouse = useRef({ x: -9999, y: -9999 })
  const scrollRef = useScrollProgressRef()

  const points = useMemo(
    () => clusteredField(count, { zMin, zMax, spread, clusterCount: 4, clusterRatio: 0.55 }),
    [count, zMin, zMax, spread]
  )
  const edges = useMemo(() => buildLayerEdges(points, k), [points, k])
  const adjacency = useMemo(() => buildAdjacency(points.length, edges), [points.length, edges])
  const baseLineColor = useMemo(() => new THREE.Color(colorLine), [colorLine])
  const prevScroll = useRef(0)

  const positions = useMemo(() => new Float32Array(points.length * 3), [points])
  const sizes = useMemo(() => new Float32Array(points.length), [points])
  const edgePositions = useMemo(() => new Float32Array(edges.length * 6), [edges])
  const edgeColors = useMemo(() => new Float32Array(edges.length * 6), [edges])

  useEffect(() => {
    if (!cursorReactive) return
    const onMove = (e) => {
      mouse.current.x = (e.clientX / window.innerWidth) * 2 - 1
      mouse.current.y = -((e.clientY / window.innerHeight) * 2 - 1)
    }
    const onLeave = () => {
      mouse.current.x = -9999
      mouse.current.y = -9999
    }
    window.addEventListener('mousemove', onMove, { passive: true })
    window.addEventListener('mouseleave', onLeave, { passive: true })
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseleave', onLeave)
    }
  }, [cursorReactive])

  useFrame((state, delta) => {
    const fovRad = (camera.fov * Math.PI) / 180

    // Scrolling makes the network feel briefly more energetic — a subtle
    // burst of activity while the visitor is actively moving through it.
    const scrollDelta = Math.abs(scrollRef.current - prevScroll.current)
    prevScroll.current = scrollRef.current
    const scrollEnergy = Math.min(scrollDelta * 500, 1)

    for (let i = 0; i < points.length; i++) {
      const p = points[i]
      if (!reduced) {
        p.phase += delta * p.speed
        if (Math.random() < CONFIG.twinkleChance * 0.6 + scrollEnergy * 0.01) {
          p.flare = 1
          // Energy pulse: a flaring node briefly lights up one of its
          // existing connections' neighbors too, so brightness appears
          // to travel along the network rather than flashing in isolation.
          const neighbors = adjacency[i]
          if (neighbors.length) {
            const n = neighbors[Math.floor(Math.random() * neighbors.length)]
            points[n].flare = Math.max(points[n].flare, 0.55)
          }
        }
        p.flare *= 0.95
      }
      let x = p.baseX + Math.sin(p.phase) * p.amp
      let y = p.baseY + Math.cos(p.phase * 0.8) * p.amp
      let z = p.z

      if (gravity && !reduced) {
        x += p.gx
        y += p.gy
        z += p.gz

        const dx = BLACK_HOLE.x - x
        const dy = BLACK_HOLE.y - y
        const dz = BLACK_HOLE.z - z
        const dist = Math.sqrt(dx * dx + dy * dy + dz * dz)

        if (dist < BLACK_HOLE.horizonRadius) {
          p.baseX = (Math.random() - 0.5) * spread * 1.6
          p.baseY = (Math.random() - 0.5) * spread * 1.1
          p.gx = 0
          p.gy = 0
          p.gz = 0
          x = p.baseX
          y = p.baseY
          z = zMin + Math.random() * (zMax - zMin)
        } else if (dist < BLACK_HOLE.pullRadius) {
          const intensity = 0.35 + scrollRef.current * 1.1
          const pull = Math.pow(1 - dist / BLACK_HOLE.pullRadius, 2) * BLACK_HOLE.gravityStrength * intensity
          p.gx += (dx / dist) * pull
          p.gy += (dy / dist) * pull
          p.gz += (dz / dist) * pull
        }
      }

      if (cursorReactive && !reduced && mouse.current.x > -999) {
        const dist = camera.position.z - z
        const halfH = Math.tan(fovRad / 2) * dist
        const halfW = halfH * (size.width / size.height)
        const worldMouseX = camera.position.x + mouse.current.x * halfW
        const worldMouseY = camera.position.y + mouse.current.y * halfH
        const dx = x - worldMouseX
        const dy = y - worldMouseY
        const d = Math.sqrt(dx * dx + dy * dy)
        if (d < CONFIG.cursorRadius && d > 0.001) {
          const push = (1 - d / CONFIG.cursorRadius) * CONFIG.cursorStrength
          x += (dx / d) * push
          y += (dy / d) * push
          // The network "wakes up" where the cursor is nearby, not just moves.
          p.flare = Math.max(p.flare, (1 - d / CONFIG.cursorRadius) * 0.85)
        }
      }

      p.x = x
      p.y = y
      p.z = z
      const tw = 0.75 + Math.sin(p.phase * 1.3) * 0.25 + p.flare * 1.6
      p.tw = tw
      positions[i * 3] = x
      positions[i * 3 + 1] = y
      positions[i * 3 + 2] = z
      sizes[i] = p.size * tw
    }

    if (pointsRef.current) {
      pointsRef.current.geometry.attributes.position.needsUpdate = true
      pointsRef.current.geometry.attributes.aSize.needsUpdate = true
    }

    // Slow ambient "breathing" applied on top of the existing connection
    // opacity, plus a lift while the visitor is scrolling.
    const breath = 0.85 + Math.sin(state.clock.elapsedTime * 0.6) * 0.15 + scrollEnergy * 0.25

    for (let e = 0; e < edges.length; e++) {
      const [a, b] = edges[e]
      const pa = points[a]
      const pb = points[b]
      edgePositions[e * 6] = pa.x
      edgePositions[e * 6 + 1] = pa.y
      edgePositions[e * 6 + 2] = pa.z
      edgePositions[e * 6 + 3] = pb.x
      edgePositions[e * 6 + 4] = pb.y
      edgePositions[e * 6 + 5] = pb.z

      const brightA = Math.min((0.55 + pa.flare * 1.2) * breath, 1.8)
      const brightB = Math.min((0.55 + pb.flare * 1.2) * breath, 1.8)
      edgeColors[e * 6] = baseLineColor.r * brightA
      edgeColors[e * 6 + 1] = baseLineColor.g * brightA
      edgeColors[e * 6 + 2] = baseLineColor.b * brightA
      edgeColors[e * 6 + 3] = baseLineColor.r * brightB
      edgeColors[e * 6 + 4] = baseLineColor.g * brightB
      edgeColors[e * 6 + 5] = baseLineColor.b * brightB
    }
    if (lineRef.current) {
      lineRef.current.geometry.attributes.position.needsUpdate = true
      lineRef.current.geometry.attributes.color.needsUpdate = true
    }
  })

  return (
    <group>
      <points ref={pointsRef}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" count={points.length} array={positions} itemSize={3} />
          <bufferAttribute attach="attributes-aSize" count={points.length} array={sizes} itemSize={1} />
        </bufferGeometry>
        <GlowPointsMaterial map={glowTexture} color={colorCore} opacity={0.95} scale={0.58} />
      </points>
      <lineSegments ref={lineRef}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" count={edges.length * 2} array={edgePositions} itemSize={3} />
          <bufferAttribute attach="attributes-color" count={edges.length * 2} array={edgeColors} itemSize={3} />
        </bufferGeometry>
        <lineBasicMaterial vertexColors transparent opacity={opacityLine} />
      </lineSegments>
    </group>
  )
}

function Debris({ enabled }) {
  const { camera } = useThree()
  const slots = useMemo(
    () =>
      new Array(CONFIG.debrisSlots).fill(null).map(() => ({
        active: false,
        t: 0,
        duration: 5,
        nextSpawn: 4 + Math.random() * CONFIG.debrisMaxDelay,
        start: new THREE.Vector3(),
        end: new THREE.Vector3(),
        rotSpeed: (Math.random() - 0.5) * 2,
      })),
    []
  )
  const meshRefs = useRef([])

  useFrame((state, delta) => {
    if (!enabled) return
    slots.forEach((s, i) => {
      const mesh = meshRefs.current[i]
      if (!mesh) return

      if (!s.active) {
        s.nextSpawn -= delta
        if (s.nextSpawn <= 0) {
          s.active = true
          s.t = 0
          s.duration = CONFIG.debrisDuration[0] + Math.random() * (CONFIG.debrisDuration[1] - CONFIG.debrisDuration[0])
          const camZ = camera.position.z
          s.start.set((Math.random() - 0.5) * 10, (Math.random() - 0.5) * 6, camZ - 22 - Math.random() * 14)
          s.end.set((Math.random() - 0.5) * 3, (Math.random() - 0.5) * 2, camZ + 2.5 + Math.random() * 1.5)
        }
        mesh.visible = false
        return
      }

      s.t += delta / s.duration
      if (s.t >= 1) {
        s.active = false
        s.nextSpawn = CONFIG.debrisMinDelay + Math.random() * (CONFIG.debrisMaxDelay - CONFIG.debrisMinDelay)
        mesh.visible = false
        return
      }

      mesh.visible = true
      const eased = s.t * s.t * (3 - 2 * s.t)
      mesh.position.lerpVectors(s.start, s.end, eased)
      const scale = 0.12 + eased * eased * 1.6
      mesh.scale.setScalar(scale)
      mesh.rotation.x += delta * s.rotSpeed
      mesh.rotation.y += delta * s.rotSpeed * 0.7

      const fadeIn = Math.min(s.t / 0.12, 1)
      const fadeOut = 1 - Math.max((s.t - 0.82) / 0.18, 0)
      mesh.material.opacity = Math.min(fadeIn, fadeOut) * 0.85
    })
  })

  return (
    <group>
      {slots.map((_, i) => (
        <mesh key={i} ref={(el) => (meshRefs.current[i] = el)} visible={false}>
          <octahedronGeometry args={[0.16, 0]} />
          <meshBasicMaterial color="#baf8ff" wireframe transparent opacity={0} />
        </mesh>
      ))}
    </group>
  )
}

// Bright meteor-style streaks that cut across the screen at random angles
// and depths — some skimming the far background, some flying close enough
// to the camera to feel like they've broken the fourth wall — each a short
// fading line (bright head, invisible tail) plus a glowing point at the head.
function ShootingStars({ count, glowTexture, enabled }) {
  const { camera } = useThree()
  const lineRef = useRef()
  const headRef = useRef()

  const stars = useMemo(
    () =>
      new Array(count).fill(null).map(() => ({
        active: false,
        t: 0,
        duration: 1,
        trailLen: 2,
        nextSpawn: 1 + Math.random() * 8,
        start: new THREE.Vector3(),
        dir: new THREE.Vector3(1, 0, 0),
      })),
    [count]
  )

  const linePositions = useMemo(() => new Float32Array(count * 6), [count])
  const lineColors = useMemo(() => new Float32Array(count * 6), [count])
  const headPositions = useMemo(() => new Float32Array(count * 3), [count])
  const headSizes = useMemo(() => new Float32Array(count), [count])

  const headVec = useMemo(() => new THREE.Vector3(), [])
  const tailVec = useMemo(() => new THREE.Vector3(), [])

  useFrame((state, delta) => {
    if (!enabled) return
    const camZ = camera.position.z

    stars.forEach((s, i) => {
      if (!s.active) {
        s.nextSpawn -= delta
        if (s.nextSpawn <= 0) {
          s.active = true
          s.t = 0
          s.duration = 0.55 + Math.random() * 0.7
          s.trailLen = 1.6 + Math.random() * 2.6

          const startX = (Math.random() - 0.5) * 22
          const startY = (Math.random() - 0.5) * 13
          const startZ = camZ - 3 - Math.random() * 14
          s.start.set(startX, startY, startZ)

          const angle = Math.random() * Math.PI * 2
          s.dir.set(Math.cos(angle), Math.sin(angle) * 0.6, (Math.random() - 0.5) * 0.5).normalize()
        }
        headSizes[i] = 0
        return
      }

      s.t += delta / s.duration
      if (s.t >= 1) {
        s.active = false
        s.nextSpawn = 2.5 + Math.random() * 7.5
        headSizes[i] = 0
        lineColors[i * 6] = 0
        lineColors[i * 6 + 1] = 0
        lineColors[i * 6 + 2] = 0
        return
      }

      const travel = s.t * 16
      headVec.copy(s.start).addScaledVector(s.dir, travel)
      tailVec.copy(headVec).addScaledVector(s.dir, -s.trailLen)

      const fadeIn = Math.min(s.t / 0.12, 1)
      const fadeOut = 1 - Math.max((s.t - 0.7) / 0.3, 0)
      const fade = fadeIn * fadeOut

      linePositions[i * 6] = headVec.x
      linePositions[i * 6 + 1] = headVec.y
      linePositions[i * 6 + 2] = headVec.z
      linePositions[i * 6 + 3] = tailVec.x
      linePositions[i * 6 + 4] = tailVec.y
      linePositions[i * 6 + 5] = tailVec.z

      lineColors[i * 6] = fade
      lineColors[i * 6 + 1] = fade * 0.97
      lineColors[i * 6 + 2] = fade
      lineColors[i * 6 + 3] = 0
      lineColors[i * 6 + 4] = 0
      lineColors[i * 6 + 5] = 0

      headPositions[i * 3] = headVec.x
      headPositions[i * 3 + 1] = headVec.y
      headPositions[i * 3 + 2] = headVec.z
      headSizes[i] = 0.55 * fade
    })

    if (lineRef.current) {
      lineRef.current.geometry.attributes.position.needsUpdate = true
      lineRef.current.geometry.attributes.color.needsUpdate = true
    }
    if (headRef.current) {
      headRef.current.geometry.attributes.position.needsUpdate = true
      headRef.current.geometry.attributes.aSize.needsUpdate = true
    }
  })

  return (
    <group>
      <lineSegments ref={lineRef}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" count={count * 2} array={linePositions} itemSize={3} />
          <bufferAttribute attach="attributes-color" count={count * 2} array={lineColors} itemSize={3} />
        </bufferGeometry>
        <lineBasicMaterial vertexColors transparent opacity={0.95} blending={THREE.AdditiveBlending} depthWrite={false} />
      </lineSegments>
      <points ref={headRef}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" count={count} array={headPositions} itemSize={3} />
          <bufferAttribute attach="attributes-aSize" count={count} array={headSizes} itemSize={1} />
        </bufferGeometry>
        <GlowPointsMaterial map={glowTexture} color="#eafeff" opacity={1} scale={0.7} />
      </points>
    </group>
  )
}

function CrystalDebrisField({ count, reduced }) {
  const fillRef = useRef()
  const wireRef = useRef()
  const dummy = useMemo(() => new THREE.Object3D(), [])

  const items = useMemo(() => {
    const arr = []
    const foregroundCount = Math.max(2, Math.floor(count * 0.1))
    for (let i = 0; i < count; i++) {
      const isForeground = i < foregroundCount
      arr.push({
        x: (Math.random() - 0.5) * 42,
        y: (Math.random() - 0.5) * 22,
        z: isForeground ? 1.5 + Math.random() * 5 : -55 + Math.random() * 52,
        scale: isForeground ? 1.4 + Math.random() * 1.6 : 0.22 + Math.random() * 0.55,
        rx: Math.random() * Math.PI,
        ry: Math.random() * Math.PI,
        rz: Math.random() * Math.PI,
        spin: (Math.random() - 0.5) * 0.06,
        bobPhase: Math.random() * Math.PI * 2,
        bobSpeed: 0.12 + Math.random() * 0.18,
        bobAmp: 0.25 + Math.random() * 0.5,
      })
    }
    return arr
  }, [count])

  const applyTransforms = (elapsed) => {
    if (!fillRef.current || !wireRef.current) return
    items.forEach((it, i) => {
      const bobY = elapsed ? Math.sin(elapsed * it.bobSpeed + it.bobPhase) * it.bobAmp : 0
      dummy.position.set(it.x, it.y + bobY, it.z)
      dummy.rotation.set(it.rx, it.ry, it.rz)
      dummy.scale.setScalar(it.scale)
      dummy.updateMatrix()
      fillRef.current.setMatrixAt(i, dummy.matrix)
      wireRef.current.setMatrixAt(i, dummy.matrix)
    })
    fillRef.current.instanceMatrix.needsUpdate = true
    wireRef.current.instanceMatrix.needsUpdate = true
  }

  useEffect(() => applyTransforms(0), [items])

  useFrame((state, delta) => {
    if (reduced) return
    items.forEach((it) => {
      it.ry += it.spin * delta
    })
    applyTransforms(state.clock.elapsedTime)
  })

  return (
    <group>
      <instancedMesh ref={fillRef} args={[null, null, count]}>
        <icosahedronGeometry args={[0.4, 0]} />
        <meshBasicMaterial color="#0a1420" transparent opacity={0.88} />
      </instancedMesh>
      <instancedMesh ref={wireRef} args={[null, null, count]}>
        <icosahedronGeometry args={[0.4, 0]} />
        <meshBasicMaterial color="#5fd8ea" wireframe transparent opacity={0.3} />
      </instancedMesh>
    </group>
  )
}

// Cheap value-noise / fbm shared by the accretion disk and its lensed halo,
// used to give both a turbulent, flowing plasma look instead of a flat tint.
const BH_NOISE_GLSL = `
  float bhHash(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
  }
  float bhNoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    float a = bhHash(i);
    float b = bhHash(i + vec2(1.0, 0.0));
    float c = bhHash(i + vec2(0.0, 1.0));
    float d = bhHash(i + vec2(1.0, 1.0));
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
  }
  float bhFbm(vec2 p) {
    float v = 0.0;
    float amp = 0.5;
    for (int i = 0; i < 4; i++) {
      v += amp * bhNoise(p);
      p *= 2.03;
      amp *= 0.5;
    }
    return v;
  }
`

const BH_RING_VERTEX_SHADER = `
  varying vec2 vPos;
  void main() {
    vPos = position.xy;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`

// The accretion disk: hot white-gold near the horizon cooling to ember
// orange at the outer edge, streaked with flowing turbulence, and brighter
// on one side to suggest relativistic Doppler beaming as it spins.
const BH_DISK_FRAGMENT_SHADER = `
  ${BH_NOISE_GLSL}
  varying vec2 vPos;
  uniform float uTime;
  uniform float uInner;
  uniform float uOuter;
  uniform float uOpacity;
  uniform vec3 uColorHot;
  uniform vec3 uColorCool;

  void main() {
    float r = length(vPos);
    if (r < uInner || r > uOuter) discard;
    float rn = clamp((r - uInner) / (uOuter - uInner), 0.0, 1.0);
    float ang = atan(vPos.y, vPos.x);

    // Fine Keplerian shear streaks (high angular frequency) layered under a
    // broader flow, closer to a smooth, fast-spinning disk than a nebula.
    float flow = bhFbm(vec2(ang * 5.0, rn * 2.2 - uTime * 0.28)) * 0.55
               + bhFbm(vec2(ang * 16.0 + uTime * 0.12, rn * 3.0)) * 0.45;
    float density = mix(0.55, 1.05, smoothstep(0.15, 0.9, flow));

    // Strong relativistic Doppler beaming: the side spinning toward the
    // camera reads dramatically brighter than the receding side.
    float beam = 0.35 + 1.35 * pow(max(0.0, cos(ang)), 1.1);
    float innerGlow = (1.0 - smoothstep(0.0, 0.4, rn)) * 0.7;

    vec3 color = mix(uColorHot, uColorCool, rn) * beam + uColorHot * innerGlow * beam * 0.5;
    float edgeFade = smoothstep(0.0, 0.06, rn) * (1.0 - smoothstep(0.82, 1.0, rn));
    float alpha = density * edgeFade * uOpacity;

    gl_FragColor = vec4(color, alpha);
  }
`

// The lensed halo — light from the disk's far side bent up and over the
// horizon, the single most recognisable Interstellar/Gargantua cue. Reads
// as two bright arcs (top/bottom) rather than a uniform ring.
const BH_HALO_FRAGMENT_SHADER = `
  ${BH_NOISE_GLSL}
  varying vec2 vPos;
  uniform float uTime;
  uniform float uInner;
  uniform float uOuter;
  uniform float uOpacity;
  uniform vec3 uColor;

  void main() {
    float r = length(vPos);
    if (r < uInner || r > uOuter) discard;
    float rn = clamp((r - uInner) / (uOuter - uInner), 0.0, 1.0);
    float ang = atan(vPos.y, vPos.x);

    float flow = bhFbm(vec2(ang * 6.0 - uTime * 0.45, rn * 4.0));
    float ring = smoothstep(0.0, 0.2, rn) * (1.0 - smoothstep(0.75, 1.0, rn));
    float vertical = 0.12 + 1.6 * pow(abs(sin(ang)), 3.0);

    vec3 color = mix(uColor, vec3(1.0), clamp(vertical * 0.35, 0.0, 0.6));
    float alpha = ring * (0.4 + 0.6 * flow) * vertical * uOpacity;
    gl_FragColor = vec4(color, alpha);
  }
`

function BlackHole({ glowTexture, reduced }) {
  const { camera } = useThree()
  const groupRef = useRef()
  const diskRef = useRef()
  const glowRef = useRef()
  const rimRef = useRef()
  const haloRef = useRef()
  const scrollRef = useScrollProgressRef()

  // Colours pulled straight from the site's own theme tokens (--accent /
  // --accent-bright) rather than a generic orange accretion disk — still
  // physically sound, since the hottest plasma skews blue-white anyway.
  const diskUniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uInner: { value: BLACK_HOLE.horizonRadius * 1.08 },
      uOuter: { value: BLACK_HOLE.horizonRadius * 2.7 },
      uOpacity: { value: 0 },
      uColorHot: { value: new THREE.Color('#eafeff') },
      uColorCool: { value: new THREE.Color('#22d3ee') },
    }),
    []
  )
  // A tight, camera-facing ring hugging the horizon — a Schwarzschild
  // black hole's shadow and photon ring stay circular from every viewing
  // angle (unlike the tilted disk itself), so this billboards to the
  // camera every frame instead of following the disk's fixed tilt.
  const haloUniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uInner: { value: BLACK_HOLE.horizonRadius * 1.2 },
      uOuter: { value: BLACK_HOLE.horizonRadius * 2.3 },
      uOpacity: { value: 0 },
      uColor: { value: new THREE.Color('#baf8ff') },
    }),
    []
  )

  useFrame((state, delta) => {
    const t = scrollRef.current
    // Prominent through the hero, fades out once the visitor scrolls into
    // the content sections so it never competes with readable text.
    const fade = 1 - Math.min(t / 0.06, 1)
    const flicker = reduced ? 0 : Math.sin(state.clock.elapsedTime * 2.3) * 0.06 + Math.sin(state.clock.elapsedTime * 5.1) * 0.03

    if (!reduced && diskRef.current) diskRef.current.rotation.z += delta * 0.18
    // The halo billboards to the camera every frame (its own swirl comes
    // from the shader's internal uTime-driven flow, not mesh rotation) so
    // the lensed ring stays circular around the horizon from any angle.
    if (haloRef.current) haloRef.current.quaternion.copy(camera.quaternion)

    diskUniforms.uTime.value = state.clock.elapsedTime
    haloUniforms.uTime.value = state.clock.elapsedTime
    diskUniforms.uOpacity.value = Math.min(0.95 + t * 0.3 + flicker, 1.2) * fade
    haloUniforms.uOpacity.value = Math.min(0.7 + t * 0.3 + flicker * 1.4, 1.15) * fade

    if (diskRef.current) diskRef.current.scale.setScalar(1 + t * 0.55)
    if (haloRef.current) haloRef.current.scale.setScalar(1 + t * 0.3)

    if (glowRef.current) {
      glowRef.current.material.opacity = (0.4 + t * 0.35 + flicker) * fade
      glowRef.current.scale.setScalar(9 + t * 4)
    }
    if (rimRef.current) {
      rimRef.current.material.opacity = (0.55 + t * 0.3 + flicker * 1.5) * fade
    }
    if (groupRef.current) {
      groupRef.current.visible = fade > 0.01
    }
  })

  return (
    <group ref={groupRef} position={[BLACK_HOLE.x, BLACK_HOLE.y, BLACK_HOLE.z]}>
      <sprite ref={glowRef} scale={[9, 9, 1]}>
        <spriteMaterial map={glowTexture} color="#8fe9f7" transparent opacity={0.35} depthWrite={false} blending={THREE.AdditiveBlending} />
      </sprite>
      <mesh ref={haloRef}>
        <ringGeometry args={[haloUniforms.uInner.value, haloUniforms.uOuter.value, 96]} />
        <shaderMaterial
          transparent
          depthWrite={false}
          side={THREE.DoubleSide}
          blending={THREE.AdditiveBlending}
          uniforms={haloUniforms}
          vertexShader={BH_RING_VERTEX_SHADER}
          fragmentShader={BH_HALO_FRAGMENT_SHADER}
        />
      </mesh>
      <mesh ref={diskRef} rotation={[Math.PI / 2.2, 0.15, 0]}>
        <ringGeometry args={[diskUniforms.uInner.value, diskUniforms.uOuter.value, 128]} />
        <shaderMaterial
          transparent
          depthWrite={false}
          side={THREE.DoubleSide}
          blending={THREE.AdditiveBlending}
          uniforms={diskUniforms}
          vertexShader={BH_RING_VERTEX_SHADER}
          fragmentShader={BH_DISK_FRAGMENT_SHADER}
        />
      </mesh>
      <mesh>
        <sphereGeometry args={[BLACK_HOLE.horizonRadius, 40, 40]} />
        <meshBasicMaterial color="#000000" />
      </mesh>
      <mesh ref={rimRef}>
        <ringGeometry args={[BLACK_HOLE.horizonRadius * 0.97, BLACK_HOLE.horizonRadius * 1.18, 72]} />
        <meshBasicMaterial color="#ffffff" transparent opacity={0.85} side={THREE.DoubleSide} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
    </group>
  )
}

function CameraRig({ reduced }) {
  const { camera } = useThree()
  const scrollProgress = useRef(0)
  const mouse = useRef({ x: 0, y: 0 })

  useEffect(() => {
    const onScroll = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight
      scrollProgress.current = max > 0 ? Math.min(window.scrollY / max, 1) : 0
    }
    const onMove = (e) => {
      mouse.current.x = (e.clientX / window.innerWidth) * 2 - 1
      mouse.current.y = -((e.clientY / window.innerHeight) * 2 - 1)
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('mousemove', onMove, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('mousemove', onMove)
    }
  }, [])

  useFrame(() => {
    const targetZ = reduced ? 8 : 8 - scrollProgress.current * CONFIG.scrollTravel
    const targetX = reduced ? 0 : mouse.current.x * 1.1
    const targetY = reduced ? 0 : mouse.current.y * 0.7

    camera.position.z += (targetZ - camera.position.z) * 0.035
    camera.position.x += (targetX - camera.position.x) * 0.04
    camera.position.y += (targetY - camera.position.y) * 0.04
    camera.lookAt(camera.position.x * 0.3, camera.position.y * 0.3, camera.position.z - 12)
  })

  return null
}

function Scene({ tier, reduced, bloomEnabled }) {
  const glowTexture = useGlowTexture()
  const sparkleTexture = useSparkleTexture()
  const counts = {
    dust: CONFIG.dust[tier],
    mid: CONFIG.mid[tier],
    near: CONFIG.near[tier],
    crystals: CONFIG.crystals[tier],
    stars: CONFIG.stars[tier],
    sparkles: CONFIG.sparkles[tier],
    shootingStars: CONFIG.shootingStars[tier],
  }

  return (
    <>
      <fog attach="fog" args={['#030607', 10, 62]} />
      <CameraRig reduced={reduced} />
      <StarField count={counts.stars} glowTexture={glowTexture} reduced={reduced} />
      <SparkleField count={counts.sparkles} sparkleTexture={sparkleTexture} reduced={reduced} />
      <DustLayer count={counts.dust} glowTexture={glowTexture} reduced={reduced} />
      <NetworkLayer
        count={counts.mid}
        zMin={-30}
        zMax={-9}
        spread={20}
        k={CONFIG.midConnections}
        glowTexture={glowTexture}
        cursorReactive={false}
        reduced={reduced}
        colorCore="#9fe9f2"
        colorLine="#22d3ee"
        opacityLine={0.16}
        gravity
      />
      <NetworkLayer
        count={counts.near}
        zMin={-9}
        zMax={-1.5}
        spread={11}
        k={CONFIG.nearConnections}
        glowTexture={glowTexture}
        cursorReactive
        reduced={reduced}
        colorCore="#eafeff"
        colorLine="#7ff3ff"
        opacityLine={0.26}
        gravity
      />
      <CrystalDebrisField count={counts.crystals} reduced={reduced} />
      <BlackHole glowTexture={glowTexture} reduced={reduced} />
      <Debris enabled={!reduced} />
      <ShootingStars count={counts.shootingStars} glowTexture={glowTexture} enabled={!reduced} />
      {bloomEnabled && (
        <EffectComposer>
          <Bloom intensity={1.0} luminanceThreshold={0.32} luminanceSmoothing={0.35} mipmapBlur radius={0.5} height={360} />
        </EffectComposer>
      )}
    </>
  )
}

function useTier() {
  const [tier, setTier] = useState('desktop')
  useEffect(() => {
    const compute = () => {
      const w = window.innerWidth
      if (w < 640) setTier('mobile')
      else if (w < 1024) setTier('tablet')
      else setTier('desktop')
    }
    compute()
    let timer = null
    const onResize = () => {
      clearTimeout(timer)
      timer = setTimeout(compute, 200)
    }
    window.addEventListener('resize', onResize, { passive: true })
    return () => window.removeEventListener('resize', onResize)
  }, [])
  return tier
}

export default function ParticleField() {
  const reduced = usePrefersReducedMotion()
  const tier = useTier()
  const [visible, setVisible] = useState(!document.hidden)

  useEffect(() => {
    const onVisibility = () => setVisible(!document.hidden)
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [])

  return (
    <div className="particle-canvas" aria-hidden="true">
      {visible && (
        <Canvas
          camera={{ position: [0, 0, 8], fov: 58, near: 0.1, far: 90 }}
          dpr={[1, tier === 'mobile' ? 1 : 1.3]}
          gl={{ antialias: false, powerPreference: 'high-performance' }}
          frameloop={visible ? 'always' : 'never'}
        >
          <Scene tier={tier} reduced={reduced} bloomEnabled={tier !== 'mobile'} />
        </Canvas>
      )}
    </div>
  )
}
