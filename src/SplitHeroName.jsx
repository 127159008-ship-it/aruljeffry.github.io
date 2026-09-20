import { useEffect, useRef } from 'react'
import gsap from 'gsap'
import usePrefersReducedMotion from './usePrefersReducedMotion'

export default function SplitHeroName({ text, className, as: Tag = 'h1', delayOffset = 0 }) {
  const containerRef = useRef(null)
  const prefersReducedMotion = usePrefersReducedMotion()

  useEffect(() => {
    const chars = containerRef.current.querySelectorAll('.char')
    if (prefersReducedMotion) {
      gsap.set(chars, { opacity: 1, y: 0, rotateX: 0, filter: 'blur(0px)' })
      return
    }
    gsap.fromTo(
      chars,
      { opacity: 0, y: 40, rotateX: -60, filter: 'blur(6px)' },
      {
        opacity: 1,
        y: 0,
        rotateX: 0,
        filter: 'blur(0px)',
        duration: 0.7,
        stagger: 0.035,
        delay: 0.15 + delayOffset,
        ease: 'back.out(1.6)',
      }
    )
  }, [prefersReducedMotion, delayOffset])

  return (
    <Tag className={className} ref={containerRef} style={{ perspective: 600 }}>
      {text.split('').map((ch, i) => (
        <span className="char" key={i} style={{ display: 'inline-block' }}>
          {ch === ' ' ? ' ' : ch}
        </span>
      ))}
    </Tag>
  )
}
