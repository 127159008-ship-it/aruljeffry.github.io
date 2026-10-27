import { motion } from 'framer-motion'
import gsap from 'gsap'
import './App.css'
import ParticleField from './ParticleField'
import BlackHole from './BlackHole'
import SmoothScroll from './SmoothScroll'
import CustomCursor from './CustomCursor'
import ScrollProgress from './ScrollProgress'
import MagneticButton from './MagneticButton'
import ParticleTextIntro from './ParticleTextIntro'
import useIsDesktop from './useIsDesktop'
import usePrefersReducedMotion from './usePrefersReducedMotion'
import { skillGroups, projects, timeline, certifications, contactLinks, resumeUrl, stats } from './content'

const cornerLabels = [
  { key: 'topLeft', className: 'corner-label corner-top-left', lines: ['CIRCUITS', 'POWER', 'PEOPLE', 'A BRIGHTER TOMORROW'] },
  { key: 'bottomLeft', className: 'corner-label corner-bottom-left', lines: ['ELECTRICAL AND', 'ELECTRONICS ENGINEERING'] },
  { key: 'topRight', className: 'corner-label corner-top-right', lines: ['EXPLORE', 'INNOVATE', 'DESIGN', 'SUSTAIN'] },
  { key: 'bottomRight', className: 'corner-label corner-bottom-right', lines: ['IDEAS', 'FLOW', 'BEYOND', 'LIMITS'] },
]

function Reveal({ children, delay = 0, className = '', onMouseMove, onMouseLeave }) {
  return (
    <motion.div
      className={className}
      onMouseMove={onMouseMove}
      onMouseLeave={onMouseLeave}
      initial={{ opacity: 0, y: 36, scale: 0.94, filter: 'blur(4px)' }}
      whileInView={{ opacity: 1, y: 0, scale: 1, filter: 'blur(0px)' }}
      viewport={{ once: false, amount: 0.3, margin: '-60px' }}
      transition={{ duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  )
}

function SplitWords({ text, stagger = 0.05 }) {
  const words = String(text).split(' ')
  return words.map((word, i) => (
    <span className="word-mask" key={`${word}-${i}`}>
      <motion.span
        className="word-inner"
        initial={{ y: '105%', opacity: 0, rotateZ: 6 }}
        whileInView={{ y: '0%', opacity: 1, rotateZ: 0 }}
        viewport={{ once: false, amount: 0.7 }}
        transition={{ duration: 0.5, delay: i * stagger, ease: [0.22, 1, 0.36, 1] }}
      >
        {word}
        {i < words.length - 1 ? ' ' : ''}
      </motion.span>
    </span>
  ))
}

function SectionFrame({ index, eyebrow, heading, children, className = '' }) {
  return (
    <div className={`section-frame ${className}`}>
      <span className="frame-index">{index}</span>
      <div className="section-head">
        <Reveal delay={0}><p className="eyebrow">{eyebrow}</p></Reveal>
        {typeof heading === 'string' ? (
          <h2 className="display-heading">
            <SplitWords text={heading} />
          </h2>
        ) : (
          <Reveal delay={0.08}>
            <h2 className="display-heading">{heading}</h2>
          </Reveal>
        )}
      </div>
      {children}
    </div>
  )
}

function App() {
  const isDesktop = useIsDesktop()
  const prefersReducedMotion = usePrefersReducedMotion()

  const handleRowMove = (e) => {
    const el = e.currentTarget
    const rect = el.getBoundingClientRect()
    const px = (e.clientX - rect.left) / rect.width
    const py = (e.clientY - rect.top) / rect.height
    el.style.setProperty('--mx', `${px * 100}%`)
    el.style.setProperty('--my', `${py * 100}%`)

    if (!isDesktop || prefersReducedMotion) return
    gsap.to(el, {
      rotateX: (0.5 - py) * 6,
      rotateY: (px - 0.5) * 6,
      transformPerspective: 1000,
      duration: 0.4,
      ease: 'power3.out',
    })
  }

  const handleRowLeave = (e) => {
    gsap.to(e.currentTarget, { rotateX: 0, rotateY: 0, duration: 0.6, ease: 'power3.out' })
  }

  const handleGlowMove = (e) => {
    const el = e.currentTarget
    const rect = el.getBoundingClientRect()
    el.style.setProperty('--mx', `${((e.clientX - rect.left) / rect.width) * 100}%`)
    el.style.setProperty('--my', `${((e.clientY - rect.top) / rect.height) * 100}%`)
  }

  return (
    <SmoothScroll>
      <CustomCursor />
      <ScrollProgress />
      <ParticleField />

      <nav className="nav">
        <div className="nav-inner">
          <a className="nav-logo" href="#top">AJ</a>
          <ul className="nav-links">
            <li><a href="#top">Home</a></li>
            <li><a href="#about">About</a></li>
            <li><a href="#projects">Projects</a></li>
            <li><a href="#skills">Skills</a></li>
            <li><a href="#contact">Contact</a></li>
          </ul>
          <MagneticButton as="a" className="btn btn-connect" href="#contact">Let&apos;s Connect ↗</MagneticButton>
        </div>
      </nav>

      <header className="hero" id="top">
        <div className="hero-blackhole" aria-hidden="true">
          <BlackHole />
        </div>
        {cornerLabels.map((group, gi) => (
          <motion.div
            key={group.key}
            className={group.className}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1, delay: 1 + gi * 0.15 }}
          >
            {group.lines.map((line) => (
              <span key={line}>{line}</span>
            ))}
            <i className="corner-rule" />
          </motion.div>
        ))}

        <motion.p
          className="hero-eyebrow"
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          ENGINEER · LEARNER · BUILDER
        </motion.p>
        <h1 className="hero-name">
          <ParticleTextIntro as="span" className="hero-name-accent" text="ARUL JEFFRY A" />
        </h1>
        <motion.p
          className="hero-tagline"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.4 }}
        >
          TURNING IDEAS INTO A SMARTER TOMORROW
        </motion.p>
        <motion.div
          className="hero-row"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.55 }}
        >
          <span className="status-pill">
            <span className="pulse-dot" />
            Open to: <strong>Graduate Engineer Trainee</strong> roles
          </span>
        </motion.div>
        <motion.div
          className="hero-row"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.65 }}
        >
          <MagneticButton className="btn btn-primary" href="#projects">See My Work →</MagneticButton>
          <MagneticButton className="btn btn-secondary" href={resumeUrl} target="_blank" rel="noreferrer">Download Résumé ⬇</MagneticButton>
          <MagneticButton className="btn btn-tertiary" href="#contact">Let&apos;s Connect ↗</MagneticButton>
        </motion.div>

        <motion.div
          className="scroll-indicator"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.9 }}
        >
          SCROLL TO EXPLORE
          <span className="scroll-mouse"><span className="scroll-mouse-dot" /></span>
        </motion.div>
      </header>

      <main>
        <section id="about" className="about-section">
          <SectionFrame index="01" eyebrow="About" heading={<>Engineering systems<br />that carry real power.</>}>
            <div className="about-grid">
              <Reveal delay={0.1} className="about-copy">
                <p>
                  I'm an Electrical &amp; Electronics Engineering student specializing in Smart Grid
                  and Electric Vehicles at SASTRA Deemed to be University, Thanjavur. My work centers
                  on DC-DC power conversion, closed-loop control design, and embedded firmware for
                  power electronic systems — from duty-cycle and component calculations through to
                  MATLAB/Simulink modeling, C2000 firmware, and multi-layer PCB fabrication in KiCad.
                </p>
                <p>
                  I've also spent time on the power-systems side through an internship covering energy
                  metering, protection equipment, and SCADA-based substation monitoring.
                </p>
              </Reveal>
              <Reveal delay={0.2} className="about-stats">
                {stats.map((s) => (
                  <div className="stat-row" key={s.label}>
                    <span className="stat-value">{s.value}</span>
                    <span className="stat-label">{s.label}</span>
                  </div>
                ))}
              </Reveal>
            </div>
          </SectionFrame>
        </section>

        <section id="skills" className="skills-section">
          <SectionFrame index="02" eyebrow="Skills" heading="Systems I work across.">
            <div className="spec-sheet">
              {skillGroups.map((group, i) => (
                <Reveal key={group.title} delay={i * 0.05} className="spec-row" onMouseMove={handleGlowMove}>
                  <span className="spec-index">{String(i + 1).padStart(2, '0')}</span>
                  <span className="spec-title">{group.title}</span>
                  <div className="spec-tags">
                    {group.items.map((item) => (
                      <span className="spec-tag" key={item}>{item}</span>
                    ))}
                  </div>
                </Reveal>
              ))}
            </div>
          </SectionFrame>
        </section>

        <section id="projects" className="projects-section">
          <SectionFrame index="03" eyebrow="Projects" heading="Selected engineering work.">
            <div className="project-rows">
              {projects.map((p, i) => (
                <Reveal key={p.title} delay={i * 0.06}>
                  <article
                    className={`project-row ${i % 2 === 1 ? 'project-row-reverse' : ''}`}
                    onMouseMove={handleRowMove}
                    onMouseLeave={handleRowLeave}
                  >
                    <span className="project-index">{String(i + 1).padStart(2, '0')}</span>
                    <div className="project-body">
                      <span className="project-tag">{p.tag}</span>
                      <h3>{p.title}</h3>
                      <p className="project-meta">{p.meta}</p>
                      <p className="project-desc">{p.desc}</p>
                      {p.report && (
                        <a className="project-link" href={p.report} target="_blank" rel="noreferrer">
                          Read full report →
                        </a>
                      )}
                    </div>
                  </article>
                </Reveal>
              ))}
            </div>
          </SectionFrame>
        </section>

        <section id="experience" className="timeline-section">
          <SectionFrame index="04" eyebrow="Path" heading="Experience & education.">
            <div className="timeline">
              {timeline.map((t, i) => (
                <Reveal key={t.title} delay={i * 0.08} className="timeline-entry">
                  <div className="timeline-marker" />
                  <div className="timeline-content">
                    <span className="timeline-kind">{t.kind} · {t.period}</span>
                    <h3>{t.title}</h3>
                    <span className="timeline-org">{t.org}</span>
                    {t.points.length > 0 && (
                      <ul>
                        {t.points.map((pt) => (
                          <li key={pt}>{pt}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </Reveal>
              ))}
            </div>
            <Reveal delay={0.3} className="cert-strip">
              <span className="cert-strip-label">Certifications</span>
              <div className="cert-strip-list">
                {certifications.map((c) => (
                  <span className="cert-chip" key={c}>{c}</span>
                ))}
              </div>
            </Reveal>
          </SectionFrame>
        </section>

        <section id="contact" className="contact-section">
          <SectionFrame index="05" eyebrow="Contact" heading={<>Let&apos;s build something<br />that matters.</>}>
            <Reveal delay={0.15} className="contact-links">
              {contactLinks.map((c) =>
                c.href ? (
                  <a
                    className="contact-link"
                    href={c.href}
                    target={c.href.startsWith('http') ? '_blank' : undefined}
                    rel="noreferrer"
                    key={c.label}
                  >
                    <span className="contact-link-label">{c.label}</span>
                    <span className="contact-link-value">{c.value}</span>
                  </a>
                ) : (
                  <div className="contact-link" key={c.label}>
                    <span className="contact-link-label">{c.label}</span>
                    <span className="contact-link-value">{c.value}</span>
                  </div>
                )
              )}
            </Reveal>
            <Reveal delay={0.3}>
              <MagneticButton className="btn btn-primary contact-cta" href="mailto:aruljeffry.2005a@gmail.com">
                Say Hello →
              </MagneticButton>
            </Reveal>
          </SectionFrame>
        </section>
      </main>

      <footer className="site-footer">
        © {new Date().getFullYear()} Arul Jeffry A — Electrical &amp; Electronics Engineering
      </footer>
    </SmoothScroll>
  )
}

export default App
