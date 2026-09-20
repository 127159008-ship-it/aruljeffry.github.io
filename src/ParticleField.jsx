import { useMemo, useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { EffectComposer, Bloom } from '@react-three/postprocessing'
import * as THREE from 'three'

function useGlowTexture() {
  return useMemo(() => {
    const size = 128
    const canvas = document.createElement('canvas')
    canvas.width = size
    canvas.height = size
    const ctx = canvas.getContext('2d')
    const gradient = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
    gradient.addColorStop(0, 'rgba(255,255,255,1)')
    gradient.addColorStop(0.35, 'rgba(255,255,255,0.7)')
    gradient.addColorStop(1, 'rgba(255,255,255,0)')
    ctx.fillStyle = gradient
    ctx.fillRect(0, 0, size, size)
    const texture = new THREE.CanvasTexture(canvas)
    texture.needsUpdate = true
    return texture
  }, [])
}

function generateNodes(count) {
  const nodes = []
  for (let i = 0; i < count; i++) {
    const x = (Math.random() - 0.5) * 30
    const z = -Math.random() * 34
    const y = -2.2 + Math.random() * 3.2 - z * 0.04
    nodes.push(new THREE.Vector3(x, y, z))
  }
  return nodes
}

function buildEdges(nodes, hubIndices) {
  const hubSet = new Set(hubIndices)
  const edgeSet = new Set()
  const edges = []

  nodes.forEach((node, i) => {
    const k = hubSet.has(i) ? 9 : 2
    const distances = nodes
      .map((other, j) => (i === j ? null : { j, d: node.distanceToSquared(other) }))
      .filter(Boolean)
      .sort((a, b) => a.d - b.d)
      .slice(0, k)

    distances.forEach(({ j }) => {
      const key = i < j ? `${i}-${j}` : `${j}-${i}`
      if (!edgeSet.has(key)) {
        edgeSet.add(key)
        edges.push([node, nodes[j]])
      }
    })
  })
  return edges
}

function Network({ count = 170 }) {
  const groupRef = useRef()
  const coreMatRef = useRef()
  const glowTexture = useGlowTexture()

  const nodes = useMemo(() => generateNodes(count), [count])
  const hubIndices = useMemo(() => {
    const idx = new Set()
    while (idx.size < 6) idx.add(Math.floor(Math.random() * nodes.length))
    return idx
  }, [nodes])
  const edges = useMemo(() => buildEdges(nodes, hubIndices), [nodes, hubIndices])

  const positions = useMemo(() => {
    const arr = new Float32Array(nodes.length * 3)
    nodes.forEach((n, i) => {
      arr[i * 3] = n.x
      arr[i * 3 + 1] = n.y
      arr[i * 3 + 2] = n.z
    })
    return arr
  }, [nodes])

  const hubPositions = useMemo(() => {
    const arr = []
    hubIndices.forEach((i) => {
      const n = nodes[i]
      arr.push(n.x, n.y, n.z)
    })
    return new Float32Array(arr)
  }, [nodes, hubIndices])

  const edgePositions = useMemo(() => {
    const arr = new Float32Array(edges.length * 6)
    edges.forEach(([a, b], i) => {
      arr[i * 6] = a.x
      arr[i * 6 + 1] = a.y
      arr[i * 6 + 2] = a.z
      arr[i * 6 + 3] = b.x
      arr[i * 6 + 4] = b.y
      arr[i * 6 + 5] = b.z
    })
    return arr
  }, [edges])

  const clock = useRef(0)

  useFrame((state, delta) => {
    clock.current += delta
    if (groupRef.current) {
      groupRef.current.position.z = Math.sin(clock.current * 0.08) * 1.5
    }
    if (coreMatRef.current) {
      coreMatRef.current.opacity = 0.8 + Math.sin(clock.current * 1.1) * 0.15
    }
  })

  return (
    <group ref={groupRef}>
      <points>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" count={nodes.length} array={positions} itemSize={3} />
        </bufferGeometry>
        <pointsMaterial
          ref={coreMatRef}
          size={0.55}
          color="#7ff3ff"
          map={glowTexture}
          transparent
          opacity={0.95}
          sizeAttenuation
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
      <points>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" count={nodes.length} array={positions} itemSize={3} />
        </bufferGeometry>
        <pointsMaterial
          size={1.6}
          color="#22d3ee"
          map={glowTexture}
          transparent
          opacity={0.28}
          sizeAttenuation
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
      <points>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" count={hubIndices.size} array={hubPositions} itemSize={3} />
        </bufferGeometry>
        <pointsMaterial
          size={1.4}
          color="#eafeff"
          map={glowTexture}
          transparent
          opacity={1}
          sizeAttenuation
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
      <lineSegments>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" count={edges.length * 2} array={edgePositions} itemSize={3} />
        </bufferGeometry>
        <lineBasicMaterial color="#22d3ee" transparent opacity={0.3} />
      </lineSegments>
    </group>
  )
}

function CursorCamera() {
  const { camera } = useThree()
  const target = useRef(new THREE.Vector3(0, -1.2, -14))

  useFrame((state) => {
    const px = state.pointer.x
    const py = state.pointer.y
    const desiredX = px * 3.2
    const desiredY = 1.1 + py * 1.1
    camera.position.x += (desiredX - camera.position.x) * 0.04
    camera.position.y += (desiredY - camera.position.y) * 0.04
    target.current.x = px * 5
    target.current.y = -1.2 + py * 1.5
    camera.lookAt(target.current)
  })

  return null
}

export default function ParticleField() {
  return (
    <div className="particle-canvas" aria-hidden="true">
      <Canvas
        camera={{ position: [0, 1.1, 6.5], fov: 62, near: 0.1, far: 60 }}
        dpr={[1, 1.5]}
        gl={{ antialias: true }}
      >
        <fog attach="fog" args={['#030607', 6, 34]} />
        <CursorCamera />
        <Network />
        <EffectComposer>
          <Bloom intensity={2.2} luminanceThreshold={0.05} luminanceSmoothing={0.25} mipmapBlur radius={0.8} />
        </EffectComposer>
      </Canvas>
    </div>
  )
}
