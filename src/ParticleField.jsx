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

  const positions = useMemo(() => new Float32Array(points.length * 3), [points])
  const sizes = useMemo(() => new Float32Array(points.length), [points])
  const edgePositions = useMemo(() => new Float32Array(edges.length * 6), [edges])

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

    for (let i = 0; i < points.length; i++) {
      const p = points[i]
      if (!reduced) {
        p.phase += delta * p.speed
        if (Math.random() < CONFIG.twinkleChance * 0.6) p.flare = 1
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
        }
      }

      p.x = x
      p.y = y
      p.z = z
      const tw = 0.75 + Math.sin(p.phase * 1.3) * 0.25 + p.flare * 1.6
      positions[i * 3] = x
      positions[i * 3 + 1] = y
      positions[i * 3 + 2] = z
      sizes[i] = p.size * tw
    }

    if (pointsRef.current) {
      pointsRef.current.geometry.attributes.position.needsUpdate = true
      pointsRef.current.geometry.attributes.aSize.needsUpdate = true
    }

    for (let e = 0; e < edges.length; e++) {
      const [a, b] = edges[e]
      edgePositions[e * 6] = points[a].x
      edgePositions[e * 6 + 1] = points[a].y
      edgePositions[e * 6 + 2] = points[a].z
      edgePositions[e * 6 + 3] = points[b].x
      edgePositions[e * 6 + 4] = points[b].y
      edgePositions[e * 6 + 5] = points[b].z
    }
    if (lineRef.current) {
      lineRef.current.geometry.attributes.position.needsUpdate = true
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
        </bufferGeometry>
        <lineBasicMaterial color={colorLine} transparent opacity={opacityLine} />
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
      })
    }
    return arr
  }, [count])

  const applyTransforms = () => {
    if (!fillRef.current || !wireRef.current) return
    items.forEach((it, i) => {
      dummy.position.set(it.x, it.y, it.z)
      dummy.rotation.set(it.rx, it.ry, it.rz)
      dummy.scale.setScalar(it.scale)
      dummy.updateMatrix()
      fillRef.current.setMatrixAt(i, dummy.matrix)
      wireRef.current.setMatrixAt(i, dummy.matrix)
    })
    fillRef.current.instanceMatrix.needsUpdate = true
    wireRef.current.instanceMatrix.needsUpdate = true
  }

  useEffect(applyTransforms, [items])

  useFrame((state, delta) => {
    if (reduced) return
    items.forEach((it) => {
      it.ry += it.spin * delta
    })
    applyTransforms()
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

function BlackHole({ glowTexture, reduced }) {
  const groupRef = useRef()
  const diskRef = useRef()
  const glowRef = useRef()
  const rimRef = useRef()
  const scrollRef = useScrollProgressRef()

  useFrame((state, delta) => {
    const t = scrollRef.current
    // Prominent through the hero, fades out once the visitor scrolls into
    // the content sections so it never competes with readable text.
    const fade = 1 - Math.min(t / 0.06, 1)

    if (!reduced && diskRef.current) diskRef.current.rotation.z += delta * 0.18
    if (diskRef.current) {
      diskRef.current.material.opacity = (0.5 + t * 0.35) * fade
      diskRef.current.scale.setScalar(1 + t * 0.55)
    }
    if (glowRef.current) {
      glowRef.current.material.opacity = (0.4 + t * 0.35) * fade
      glowRef.current.scale.setScalar(9 + t * 4)
    }
    if (rimRef.current) {
      rimRef.current.material.opacity = (0.55 + t * 0.3) * fade
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
      <mesh rotation={[Math.PI / 2.9, 0.15, 0]}>
        <ringGeometry args={[BLACK_HOLE.horizonRadius * 1.5, BLACK_HOLE.horizonRadius * 3.4, 80]} />
        <meshBasicMaterial color="#5fd8ea" transparent opacity={0.22} side={THREE.DoubleSide} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh ref={diskRef} rotation={[Math.PI / 2.9, 0.15, 0]}>
        <ringGeometry args={[BLACK_HOLE.horizonRadius * 1.1, BLACK_HOLE.horizonRadius * 1.85, 80]} />
        <meshBasicMaterial color="#e2fbff" transparent opacity={0.85} side={THREE.DoubleSide} blending={THREE.AdditiveBlending} depthWrite={false} />
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
  const counts = {
    dust: CONFIG.dust[tier],
    mid: CONFIG.mid[tier],
    near: CONFIG.near[tier],
    crystals: CONFIG.crystals[tier],
  }

  return (
    <>
      <fog attach="fog" args={['#030607', 10, 62]} />
      <CameraRig reduced={reduced} />
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
