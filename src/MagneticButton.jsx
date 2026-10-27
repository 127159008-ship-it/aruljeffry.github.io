import { useRef } from 'react'
import gsap from 'gsap'
import useIsDesktop from './useIsDesktop'
import usePrefersReducedMotion from './usePrefersReducedMotion'

export default function MagneticButton({ as: Tag = 'a', className, strength = 0.25, children, ...props }) {
  const ref = useRef(null)
  const isDesktop = useIsDesktop()
  const prefersReducedMotion = usePrefersReducedMotion()

  const onMouseMove = (e) => {
    if (!isDesktop || prefersReducedMotion || !ref.current) return
    const rect = ref.current.getBoundingClientRect()
    const relX = e.clientX - (rect.left + rect.width / 2)
    const relY = e.clientY - (rect.top + rect.height / 2)
    gsap.to(ref.current, {
      x: relX * strength,
      y: relY * strength,
      duration: 0.4,
      ease: 'power3.out',
      overwrite: 'auto',
    })
  }

  const onMouseLeave = () => {
    if (!ref.current) return
    if (!isDesktop || prefersReducedMotion) {
      gsap.set(ref.current, { x: 0, y: 0 })
      return
    }
    gsap.to(ref.current, { x: 0, y: 0, duration: 0.35, ease: 'power3.out', overwrite: 'auto' })
  }

  return (
    <Tag
      ref={ref}
      className={className}
      onMouseMove={onMouseMove}
      onMouseLeave={onMouseLeave}
      {...props}
    >
      {children}
    </Tag>
  )
}
