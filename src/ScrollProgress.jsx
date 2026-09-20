import { useEffect, useRef } from 'react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

export default function ScrollProgress() {
  const fillRef = useRef(null)

  useEffect(() => {
    const trigger = ScrollTrigger.create({
      start: 0,
      end: 'max',
      onUpdate: (self) => {
        gsap.set(fillRef.current, { scaleY: self.progress })
      },
    })
    return () => trigger.kill()
  }, [])

  return (
    <div className="scroll-progress" aria-hidden="true">
      <div className="scroll-progress-track">
        <div className="scroll-progress-fill" ref={fillRef} />
      </div>
    </div>
  )
}
