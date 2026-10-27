import { useEffect } from 'react'
import Lenis from 'lenis'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import usePrefersReducedMotion from './usePrefersReducedMotion'

gsap.registerPlugin(ScrollTrigger)

export default function SmoothScroll({ children }) {
  const prefersReducedMotion = usePrefersReducedMotion()

  useEffect(() => {
    if (prefersReducedMotion) return undefined

    const lenis = new Lenis({
      duration: 1.1,
      smoothWheel: true,
      // Let Lenis own in-page anchor navigation instead of competing with
      // the browser's native CSS smooth-scroll animation. The sticky nav is
      // accounted for so section headings are not hidden behind it.
      anchors: { offset: -80 },
    })
    const onScroll = () => ScrollTrigger.update()
    const tick = (time) => lenis.raf(time * 1000)

    lenis.on('scroll', onScroll)
    gsap.ticker.add(tick)
    // Lenis and ScrollTrigger share this ticker; disabling lag smoothing avoids
    // them disagreeing about elapsed scroll time after a dropped frame.
    gsap.ticker.lagSmoothing(0)

    return () => {
      gsap.ticker.remove(tick)
      lenis.off('scroll', onScroll)
      lenis.destroy()
    }
  }, [prefersReducedMotion])

  return children
}
