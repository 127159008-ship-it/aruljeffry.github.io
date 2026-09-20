import { useMemo, useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import * as THREE from 'three'

function generateNodes(count) {
  const nodes = []
  for (let i = 0; i < count; i++) {
    const radius = 5 + Math.random() * 9
    const theta = Math.random() * Math.PI * 2
    const phi = Math.acos(2 * Math.random() - 1)
    nodes.push(
      new THREE.Vector3(
        radius * Math.sin(phi) * Math.cos(theta),
        radius * Math.sin(phi) * Math.sin(theta),
        radius * Math.cos(phi)
      )
    )
  }
  return nodes
}

function buildEdges(nodes, k) {
  const edgeSet = new Set()
  const edges = []
  nodes.forEach((node, i) => {
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

function NeuronNetwork({ count = 100, k = 2 }) {
  const groupRef = useRef()
  const materialRef = useRef()
  const clock = useRef(0)

  const nodes = useMemo(() => generateNodes(count), [count])
  const edges = useMemo(() => buildEdges(nodes, k), [nodes, k])

  const positions = useMemo(() => {
    const arr = new Float32Array(nodes.length * 3)
    nodes.forEach((n, i) => {
      arr[i * 3] = n.x
      arr[i * 3 + 1] = n.y
      arr[i * 3 + 2] = n.z
    })
    return arr
  }, [nodes])

  useFrame((state, delta) => {
    if (!groupRef.current) return
    clock.current += delta
    groupRef.current.rotation.y += delta * 0.045
    groupRef.current.rotation.x += delta * 0.012
    groupRef.current.rotation.y += state.pointer.x * delta * 0.18
    groupRef.current.rotation.x += state.pointer.y * delta * 0.1

    if (materialRef.current) {
      materialRef.current.opacity = 0.75 + Math.sin(clock.current * 1.3) * 0.15
    }
  })

  return (
    <group ref={groupRef}>
      <points>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            count={nodes.length}
            array={positions}
            itemSize={3}
          />
        </bufferGeometry>
        <pointsMaterial
          ref={materialRef}
          size={0.08}
          color="#ff9d42"
          transparent
          opacity={0.85}
          sizeAttenuation
          depthWrite={false}
        />
      </points>
      <points>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            count={nodes.length}
            array={positions}
            itemSize={3}
          />
        </bufferGeometry>
        <pointsMaterial
          size={0.24}
          color="#ffd9a8"
          transparent
          opacity={0.18}
          sizeAttenuation
          depthWrite={false}
        />
      </points>
      {edges.map(([a, b], i) => (
        <line key={i}>
          <bufferGeometry>
            <bufferAttribute
              attach="attributes-position"
              count={2}
              array={new Float32Array([a.x, a.y, a.z, b.x, b.y, b.z])}
              itemSize={3}
            />
          </bufferGeometry>
          <lineBasicMaterial color="#ff9d42" transparent opacity={0.22} />
        </line>
      ))}
    </group>
  )
}

export default function ParticleField() {
  return (
    <div className="particle-canvas" aria-hidden="true">
      <Canvas camera={{ position: [0, 0, 9], fov: 55 }} dpr={[1, 1.5]}>
        <NeuronNetwork />
      </Canvas>
    </div>
  )
}
