import { useEffect, useRef } from 'react'
import gsap from 'gsap'
import useIsDesktop from './useIsDesktop'

export default function CustomCursor() {
  const isDesktop = useIsDesktop()
  const dotRef = useRef(null)
  const ringRef = useRef(null)

  useEffect(() => {
    if (!isDesktop) return

    const dot = dotRef.current
    const ring = ringRef.current
    if (!dot || !ring) return

    const moveDot = gsap.quickTo(dot, 'x', { duration: 0.08, ease: 'power3.out' })
    const moveDotY = gsap.quickTo(dot, 'y', { duration: 0.08, ease: 'power3.out' })
    const moveRing = gsap.quickTo(ring, 'x', { duration: 0.35, ease: 'power3.out' })
    const moveRingY = gsap.quickTo(ring, 'y', { duration: 0.35, ease: 'power3.out' })

    const onMove = (e) => {
      moveDot(e.clientX)
      moveDotY(e.clientY)
      moveRing(e.clientX)
      moveRingY(e.clientY)
    }

    const onDown = () => gsap.to(ring, { scale: 0.7, duration: 0.2 })
    const onUp = () => gsap.to(ring, { scale: 1, duration: 0.2 })

    const interactiveSelector = 'a, button, .project-card, .skill-card, .chip'
    const onEnterInteractive = () => gsap.to(ring, { scale: 1.8, duration: 0.25 })
    const onLeaveInteractive = () => gsap.to(ring, { scale: 1, duration: 0.25 })

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mousedown', onDown)
    window.addEventListener('mouseup', onUp)

    const interactiveEls = document.querySelectorAll(interactiveSelector)
    interactiveEls.forEach((el) => {
      el.addEventListener('mouseenter', onEnterInteractive)
      el.addEventListener('mouseleave', onLeaveInteractive)
    })

    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mousedown', onDown)
      window.removeEventListener('mouseup', onUp)
      interactiveEls.forEach((el) => {
        el.removeEventListener('mouseenter', onEnterInteractive)
        el.removeEventListener('mouseleave', onLeaveInteractive)
      })
    }
  }, [isDesktop])

  if (!isDesktop) return null

  return (
    <>
      <div className="cursor-dot" ref={dotRef} />
      <div className="cursor-ring" ref={ringRef} />
    </>
  )
}
