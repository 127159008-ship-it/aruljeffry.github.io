import { useEffect, useRef } from 'react'
import gsap from 'gsap'
import useIsDesktop from './useIsDesktop'
import usePrefersReducedMotion from './usePrefersReducedMotion'

export default function MagneticButton({ as: Tag = 'a', className, strength = 0.25, children, ...props }) {
  const ref = useRef(null)
  const originRef = useRef(null)
  const isDesktop = useIsDesktop()
  const prefersReducedMotion = usePrefersReducedMotion()
  const wasActiveRef = useRef(isDesktop && !prefersReducedMotion)

  useEffect(() => {
    const active = isDesktop && !prefersReducedMotion
    // If the preference or viewport changes while the button is displaced,
    // remove only GSAP's transform so CSS hover/focus styles can take over.
    if (!active && wasActiveRef.current && ref.current) {
      gsap.killTweensOf(ref.current)
      gsap.set(ref.current, { clearProps: 'transform' })
      originRef.current = null
    }
    wasActiveRef.current = active
  }, [isDesktop, prefersReducedMotion])

  const onMouseMove = (e) => {
    if (!isDesktop || prefersReducedMotion || !ref.current) return
    // Cache the untransformed center once per hover. Re-reading the bounding
    // box after applying a transform causes a feedback loop and visible wobble.
    if (!originRef.current) {
      const rect = ref.current.getBoundingClientRect()
      originRef.current = { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }
    }
    const relX = e.clientX - originRef.current.x
    const relY = e.clientY - originRef.current.y
    gsap.to(ref.current, {
      x: relX * strength,
      y: relY * strength,
      duration: 0.4,
      ease: 'power3.out',
      overwrite: 'auto',
    })
  }

  const onMouseLeave = () => {
    originRef.current = null
    if (!ref.current) return
    if (!isDesktop || prefersReducedMotion) {
      gsap.killTweensOf(ref.current)
      gsap.set(ref.current, { clearProps: 'transform' })
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
