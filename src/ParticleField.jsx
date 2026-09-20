import { useMemo, useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import * as THREE from 'three'

function Field({ count = 1400 }) {
  const pointsRef = useRef()
  const mouse = useRef({ x: 0, y: 0 })

  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3)
    for (let i = 0; i < count; i++) {
      const radius = 6 + Math.random() * 10
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(2 * Math.random() - 1)
      arr[i * 3] = radius * Math.sin(phi) * Math.cos(theta)
      arr[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta)
      arr[i * 3 + 2] = radius * Math.cos(phi)
    }
    return arr
  }, [count])

  useFrame((state, delta) => {
    if (!pointsRef.current) return
    pointsRef.current.rotation.y += delta * 0.035
    pointsRef.current.rotation.x += delta * 0.01

    mouse.current.x = state.pointer.x
    mouse.current.y = state.pointer.y
    pointsRef.current.rotation.y += mouse.current.x * delta * 0.15
    pointsRef.current.rotation.x += mouse.current.y * delta * 0.08
  })

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={count}
          array={positions}
          itemSize={3}
        />
      </bufferGeometry>
      <pointsMaterial
        size={0.045}
        color="#3fd6b8"
        transparent
        opacity={0.75}
        sizeAttenuation
        depthWrite={false}
      />
    </points>
  )
}

function Lines({ count = 60 }) {
  const groupRef = useRef()

  const segments = useMemo(() => {
    const arr = []
    for (let i = 0; i < count; i++) {
      const radius = 6 + Math.random() * 10
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(2 * Math.random() - 1)
      const x = radius * Math.sin(phi) * Math.cos(theta)
      const y = radius * Math.sin(phi) * Math.sin(theta)
      const z = radius * Math.cos(phi)
      const len = 0.6 + Math.random() * 1.2
      arr.push([
        new THREE.Vector3(x, y, z),
        new THREE.Vector3(x + len, y + len * 0.3, z),
      ])
    }
    return arr
  }, [count])

  useFrame((state, delta) => {
    if (!groupRef.current) return
    groupRef.current.rotation.y += delta * 0.035
    groupRef.current.rotation.x += delta * 0.01
  })

  return (
    <group ref={groupRef}>
      {segments.map((pts, i) => (
        <line key={i}>
          <bufferGeometry>
            <bufferAttribute
              attach="attributes-position"
              count={2}
              array={new Float32Array(pts.flatMap((p) => [p.x, p.y, p.z]))}
              itemSize={3}
            />
          </bufferGeometry>
          <lineBasicMaterial color="#3fd6b8" transparent opacity={0.18} />
        </line>
      ))}
    </group>
  )
}

export default function ParticleField() {
  return (
    <div className="particle-canvas" aria-hidden="true">
      <Canvas camera={{ position: [0, 0, 9], fov: 55 }} dpr={[1, 1.5]}>
        <Field />
        <Lines />
      </Canvas>
    </div>
  )
}
