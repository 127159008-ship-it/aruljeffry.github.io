import { useEffect, useRef } from 'react'

// Tunable configuration — kept in one place so the feel of the field can be
// adjusted without touching the render/physics logic below.
const CONFIG = {
  countDesktop: 110,
  countTablet: 70,
  countMobile: 38,
  sizeMin: 1,
  sizeMax: 2.2,
  connectionDistance: 130,
  maxConnectionsPerParticle: 5,
  connectionOpacity: 0.16,
  driftSpeed: 0.00028,
  driftAmp: 22,
  cursorRadius: 150,
  cursorStrength: 34,
  rippleDuration: 950,
  rippleMaxRadius: 260,
  rippleStrength: 30,
  structureLerp: 0.02,
  formationLerp: 0.015,
}

// Which section pulls the field into a more "designed" formation, and how
// strongly. 0 = fully organic drift, 1 = fully locked to the formation.
const SECTION_FORMATIONS = {
  top: { structure: 0, formation: 'organic' },
  about: { structure: 0.16, formation: 'grid' },
  skills: { structure: 0.38, formation: 'grid' },
  projects: { structure: 0.5, formation: 'cluster' },
  experience: { structure: 0.55, formation: 'timeline' },
  education: { structure: 0.55, formation: 'timeline' },
  certifications: { structure: 0.4, formation: 'grid' },
  contact: { structure: 0.75, formation: 'center' },
}

function getParticleCount(width) {
  if (width < 640) return CONFIG.countMobile
  if (width < 1024) return CONFIG.countTablet
  return CONFIG.countDesktop
}

function formationTarget(kind, p, width, height) {
  switch (kind) {
    case 'grid': {
      const cell = 110
      return {
        x: Math.round(p.baseX / cell) * cell,
        y: Math.round(p.baseY / cell) * cell,
      }
    }
    case 'timeline': {
      const centerX = width * 0.5
      return {
        x: centerX + p.timelineJitter,
        y: p.baseY,
      }
    }
    case 'cluster': {
      const clusterX = width * 0.62
      return {
        x: p.baseX + (clusterX - p.baseX) * 0.6,
        y: p.baseY,
      }
    }
    case 'center': {
      const cx = width * 0.5
      const cy = height * 0.5
      return {
        x: p.baseX + (cx - p.baseX) * 0.55,
        y: p.baseY + (cy - p.baseY) * 0.55,
      }
    }
    default:
      return { x: p.baseX, y: p.baseY }
  }
}

export default function ParticleField() {
  const canvasRef = useRef(null)
  const containerRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    let width = window.innerWidth
    let height = window.innerHeight
    let dpr = Math.min(window.devicePixelRatio || 1, 2)
    let particles = []
    let ripples = []
    let mouseX = -9999
    let mouseY = -9999
    let mouseActive = false
    let rafId = null
    let running = true
    let currentStructure = 0
    let targetStructure = 0

    function resize() {
      width = window.innerWidth
      height = window.innerHeight
      dpr = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = width * dpr
      canvas.height = height * dpr
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      buildParticles()
    }

    function buildParticles() {
      const count = getParticleCount(width)
      particles = new Array(count).fill(null).map(() => {
        const baseX = Math.random() * width
        const baseY = Math.random() * height
        return {
          baseX,
          baseY,
          phaseX: Math.random() * Math.PI * 2,
          phaseY: Math.random() * Math.PI * 2,
          ampX: CONFIG.driftAmp * (0.5 + Math.random() * 0.6),
          ampY: CONFIG.driftAmp * (0.5 + Math.random() * 0.6),
          speed: CONFIG.driftSpeed * (0.7 + Math.random() * 0.6),
          size: CONFIG.sizeMin + Math.random() * (CONFIG.sizeMax - CONFIG.sizeMin),
          timelineJitter: (Math.random() - 0.5) * 60,
          targetX: baseX,
          targetY: baseY,
          x: baseX,
          y: baseY,
        }
      })
    }

    function getActiveFormation() {
      const centerY = height / 2
      let closestId = 'top'
      let closestDist = Infinity
      Object.keys(SECTION_FORMATIONS).forEach((id) => {
        const el = document.getElementById(id)
        if (!el) return
        const rect = el.getBoundingClientRect()
        const mid = rect.top + rect.height / 2
        const dist = Math.abs(mid - centerY)
        if (dist < closestDist) {
          closestDist = dist
          closestId = id
        }
      })
      return SECTION_FORMATIONS[closestId] || SECTION_FORMATIONS.top
    }

    let activeFormation = SECTION_FORMATIONS.top
    let scrollTicking = false
    function onScroll() {
      if (scrollTicking) return
      scrollTicking = true
      requestAnimationFrame(() => {
        activeFormation = getActiveFormation()
        targetStructure = activeFormation.structure
        scrollTicking = false
      })
    }

    function onMouseMove(e) {
      mouseX = e.clientX
      mouseY = e.clientY
      mouseActive = true
    }

    function onMouseLeave() {
      mouseActive = false
      mouseX = -9999
      mouseY = -9999
    }

    function onClick(e) {
      ripples.push({ x: e.clientX, y: e.clientY, start: performance.now() })
      if (ripples.length > 4) ripples.shift()
    }

    function onVisibility() {
      running = !document.hidden
      if (running) {
        rafId = requestAnimationFrame(draw)
      } else if (rafId) {
        cancelAnimationFrame(rafId)
      }
    }

    function draw(now) {
      if (!running) return
      ctx.clearRect(0, 0, width, height)

      if (!prefersReducedMotion) {
        currentStructure += (targetStructure - currentStructure) * CONFIG.structureLerp
      }

      const activeRipples = ripples.filter((r) => now - r.start < CONFIG.rippleDuration)
      ripples = activeRipples

      for (let i = 0; i < particles.length; i++) {
        const p = particles[i]

        let organicX = p.baseX
        let organicY = p.baseY
        if (!prefersReducedMotion) {
          organicX = p.baseX + Math.sin(now * p.speed + p.phaseX) * p.ampX
          organicY = p.baseY + Math.cos(now * p.speed * 0.85 + p.phaseY) * p.ampY

          const ft = formationTarget(activeFormation.formation, p, width, height)
          p.targetX += (ft.x - p.targetX) * CONFIG.formationLerp
          p.targetY += (ft.y - p.targetY) * CONFIG.formationLerp
        }

        let renderX = organicX + (p.targetX - p.baseX) * currentStructure
        let renderY = organicY + (p.targetY - p.baseY) * currentStructure

        if (!prefersReducedMotion && mouseActive) {
          const dx = renderX - mouseX
          const dy = renderY - mouseY
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < CONFIG.cursorRadius && dist > 0.001) {
            const falloff = 1 - dist / CONFIG.cursorRadius
            const push = falloff * falloff * CONFIG.cursorStrength
            renderX += (dx / dist) * push
            renderY += (dy / dist) * push
          }
        }

        if (!prefersReducedMotion) {
          for (let r = 0; r < activeRipples.length; r++) {
            const ripple = activeRipples[r]
            const elapsed = now - ripple.start
            const progress = elapsed / CONFIG.rippleDuration
            const rippleRadius = progress * CONFIG.rippleMaxRadius
            const dx = renderX - ripple.x
            const dy = renderY - ripple.y
            const dist = Math.sqrt(dx * dx + dy * dy)
            const band = 40
            const distFromFront = Math.abs(dist - rippleRadius)
            if (distFromFront < band && dist > 0.001) {
              const strength = (1 - distFromFront / band) * (1 - progress) * CONFIG.rippleStrength
              renderX += (dx / dist) * strength
              renderY += (dy / dist) * strength
            }
          }
        }

        p.x = renderX
        p.y = renderY
      }

      ctx.fillStyle = 'rgba(230, 240, 242, 0.55)'
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i]
        ctx.globalAlpha = 0.75
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2)
        ctx.fill()
      }
      ctx.globalAlpha = 1

      const maxDistSq = CONFIG.connectionDistance * CONFIG.connectionDistance
      for (let i = 0; i < particles.length; i++) {
        const a = particles[i]
        let connections = 0
        for (let j = i + 1; j < particles.length; j++) {
          if (connections >= CONFIG.maxConnectionsPerParticle) break
          const b = particles[j]
          const dx = a.x - b.x
          const dy = a.y - b.y
          const distSq = dx * dx + dy * dy
          if (distSq < maxDistSq) {
            const t = 1 - distSq / maxDistSq
            ctx.strokeStyle = `rgba(210, 226, 230, ${(CONFIG.connectionOpacity * t).toFixed(3)})`
            ctx.lineWidth = 1
            ctx.beginPath()
            ctx.moveTo(a.x, a.y)
            ctx.lineTo(b.x, b.y)
            ctx.stroke()
            connections++
          }
        }
      }

      rafId = requestAnimationFrame(draw)
    }

    resize()
    activeFormation = getActiveFormation()
    targetStructure = activeFormation.structure
    currentStructure = targetStructure

    let resizeTimer = null
    function onResize() {
      clearTimeout(resizeTimer)
      resizeTimer = setTimeout(resize, 150)
    }

    window.addEventListener('resize', onResize, { passive: true })
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('mousemove', onMouseMove, { passive: true })
    window.addEventListener('mouseleave', onMouseLeave, { passive: true })
    window.addEventListener('click', onClick, { passive: true })
    document.addEventListener('visibilitychange', onVisibility)

    rafId = requestAnimationFrame(draw)

    return () => {
      running = false
      if (rafId) cancelAnimationFrame(rafId)
      window.removeEventListener('resize', onResize)
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseleave', onMouseLeave)
      window.removeEventListener('click', onClick)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])

  return (
    <div className="particle-canvas" ref={containerRef} aria-hidden="true">
      <canvas ref={canvasRef} />
    </div>
  )
}
