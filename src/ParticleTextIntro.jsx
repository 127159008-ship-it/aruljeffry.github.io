import { useEffect, useRef, useState } from 'react'
import usePrefersReducedMotion from './usePrefersReducedMotion'

function hexToRgb(hex) {
  const clean = hex.replace('#', '').trim()
  const full = clean.length === 3 ? clean.split('').map((c) => c + c).join('') : clean
  const num = parseInt(full, 16)
  if (Number.isNaN(num)) return { r: 186, g: 248, b: 255 }
  return { r: (num >> 16) & 255, g: (num >> 8) & 255, b: num & 255 }
}

function lerpColor(c1, c2, t) {
  const r = Math.round(c1.r + (c2.r - c1.r) * t)
  const g = Math.round(c1.g + (c2.g - c1.g) * t)
  const b = Math.round(c1.b + (c2.b - c1.b) * t)
  return `rgb(${r}, ${g}, ${b})`
}

const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3)
const easeOutBack = (t) => {
  const c1 = 1.70158
  const c3 = c1 + 1
  return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2)
}

// Renders `text` as thousands of tiny light-fragments that drift in from
// scattered positions and converge into the letterforms, then hands off to
// the real, crisp, selectable text underneath. Plays once on mount.
export default function ParticleTextIntro({ text, className, as: Tag = 'h1' }) {
  const textRef = useRef(null)
  const canvasRef = useRef(null)
  const prefersReducedMotion = usePrefersReducedMotion()
  const [revealed, setRevealed] = useState(prefersReducedMotion)
  const [canvasVisible, setCanvasVisible] = useState(!prefersReducedMotion)

  useEffect(() => {
    if (prefersReducedMotion) return
    const el = textRef.current
    const canvas = canvasRef.current
    if (!el || !canvas) return

    const rect = el.getBoundingClientRect()
    const width = Math.ceil(rect.width)
    const height = Math.ceil(rect.height)
    if (width < 4 || height < 4) {
      setRevealed(true)
      setCanvasVisible(false)
      return
    }

    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    canvas.width = width * dpr
    canvas.height = height * dpr
    const ctx = canvas.getContext('2d')
    ctx.scale(dpr, dpr)

    const computed = getComputedStyle(el)
    const rootStyles = getComputedStyle(document.documentElement)
    const bright = hexToRgb(rootStyles.getPropertyValue('--accent-bright').trim() || '#baf8ff')
    const base = hexToRgb(rootStyles.getPropertyValue('--accent').trim() || '#22d3ee')

    const sample = document.createElement('canvas')
    sample.width = width
    sample.height = height
    const sctx = sample.getContext('2d')
    sctx.fillStyle = '#fff'
    sctx.font = `${computed.fontWeight} ${computed.fontSize} ${computed.fontFamily}`
    sctx.textBaseline = 'alphabetic'
    const metrics = sctx.measureText(text)
    const ascent = metrics.actualBoundingBoxAscent || parseFloat(computed.fontSize) * 0.72
    const descent = metrics.actualBoundingBoxDescent || parseFloat(computed.fontSize) * 0.2
    const baselineY = (height + (ascent - descent)) / 2
    sctx.fillText(text, 0, baselineY)
    const img = sctx.getImageData(0, 0, width, height).data

    const isSmall = width < 420
    const density = isSmall ? 3 : width < 900 ? 3 : 4
    const rawTargets = []
    for (let y = 0; y < height; y += density) {
      for (let x = 0; x < width; x += density) {
        if (img[(y * width + x) * 4 + 3] > 140) rawTargets.push({ x, y })
      }
    }
    for (let i = rawTargets.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[rawTargets[i], rawTargets[j]] = [rawTargets[j], rawTargets[i]]
    }
    const maxParticles = isSmall ? 650 : 1500
    const targets = rawTargets.slice(0, maxParticles)

    if (targets.length === 0) {
      setRevealed(true)
      setCanvasVisible(false)
      return
    }

    const particles = targets.map((pt) => {
      const fromEdge = Math.random() < 0.55
      const angle = Math.random() * Math.PI * 2
      const dist = width * (0.7 + Math.random() * 2.1)
      const sx = fromEdge ? pt.x + Math.cos(angle) * dist : (Math.random() - 0.5) * width * 3.4
      const sy = fromEdge ? pt.y + Math.sin(angle) * dist * 0.6 : (Math.random() - 0.5) * height * 8
      const modeRoll = Math.random()
      return {
        sx,
        sy,
        tx: pt.x,
        ty: pt.y,
        prevX: sx,
        prevY: sy,
        delay: Math.random() * 0.55,
        dur: 0.85 + Math.random() * 0.65,
        mode: modeRoll < 0.22 ? 'orbit' : modeRoll < 0.48 ? 'overshoot' : 'direct',
        curveSign: Math.random() < 0.5 ? 1 : -1,
        size: 0.7 + Math.random() * 1.3,
        color: lerpColor(bright, base, Math.random()),
      }
    })

    let rafId = null
    let sparksSpawned = false
    let sparks = []
    const start = performance.now()
    const assembleEnd = 2.15
    const outroEnd = 2.7

    function spawnSparks() {
      const count = isSmall ? 8 : 16
      for (let i = 0; i < count; i++) {
        const src = particles[Math.floor(Math.random() * particles.length)]
        const angle = Math.random() * Math.PI * 2
        sparks.push({
          x: src.tx,
          y: src.ty,
          vx: Math.cos(angle) * (20 + Math.random() * 40),
          vy: Math.sin(angle) * (20 + Math.random() * 40) - 10,
          life: 0,
          maxLife: 0.5 + Math.random() * 0.3,
          size: 0.8 + Math.random() * 1.2,
          color: lerpColor(bright, base, Math.random()),
        })
      }
    }

    function frame(now) {
      const elapsed = (now - start) / 1000
      ctx.clearRect(0, 0, width, height)

      for (const p of particles) {
        const t = (elapsed - p.delay) / p.dur
        let x
        let y
        if (t <= 0) {
          x = p.sx + Math.sin(elapsed * 1.4 + p.ty * 0.06) * 2.4
          y = p.sy + Math.cos(elapsed * 1.1 + p.tx * 0.06) * 2.4
        } else if (t < 1) {
          const e = p.mode === 'overshoot' ? easeOutBack(t) : easeOutCubic(t)
          let lx = p.sx + (p.tx - p.sx) * e
          let ly = p.sy + (p.ty - p.sy) * e
          if (p.mode === 'orbit') {
            const bow = Math.sin(t * Math.PI) * 22 * p.curveSign * (1 - t * 0.6)
            const dx = p.tx - p.sx
            const dy = p.ty - p.sy
            const len = Math.hypot(dx, dy) || 1
            lx += (-dy / len) * bow
            ly += (dx / len) * bow
          }
          x = lx
          y = ly
        } else {
          const shimmer = Math.sin(elapsed * 3 + p.tx * 0.3) * 0.25
          x = p.tx + shimmer
          y = p.ty
        }

        ctx.globalAlpha = 0.3
        ctx.strokeStyle = p.color
        ctx.lineWidth = p.size * 0.55
        ctx.beginPath()
        ctx.moveTo(p.prevX, p.prevY)
        ctx.lineTo(x, y)
        ctx.stroke()

        ctx.globalAlpha = 0.92
        ctx.fillStyle = p.color
        ctx.beginPath()
        ctx.arc(x, y, p.size, 0, Math.PI * 2)
        ctx.fill()

        p.prevX = x
        p.prevY = y
      }

      if (elapsed >= assembleEnd && !sparksSpawned) {
        sparksSpawned = true
        spawnSparks()
        setRevealed(true)
      }

      if (sparksSpawned) {
        ctx.globalAlpha = 1
        sparks = sparks.filter((s) => s.life < s.maxLife)
        for (const s of sparks) {
          s.life += 1 / 60
          s.x += s.vx / 60
          s.y += s.vy / 60
          s.vy += 22 / 60
          const a = 1 - s.life / s.maxLife
          ctx.globalAlpha = Math.max(a, 0)
          ctx.fillStyle = s.color
          ctx.beginPath()
          ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2)
          ctx.fill()
        }
      }

      ctx.globalAlpha = 1

      if (elapsed >= outroEnd) {
        setCanvasVisible(false)
        return
      }
      rafId = requestAnimationFrame(frame)
    }

    rafId = requestAnimationFrame(frame)
    return () => {
      if (rafId) cancelAnimationFrame(rafId)
    }
  }, [prefersReducedMotion, text])

  return (
    <span style={{ position: 'relative', display: 'inline-block' }}>
      <Tag
        ref={textRef}
        className={className}
        style={{ opacity: revealed ? 1 : 0, transition: 'opacity 0.5s ease' }}
      >
        {text}
      </Tag>
      {canvasVisible && (
        <canvas
          ref={canvasRef}
          aria-hidden="true"
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            pointerEvents: 'none',
            opacity: revealed ? 0 : 1,
            transition: 'opacity 0.55s ease',
          }}
        />
      )}
    </span>
  )
}
