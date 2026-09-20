import { motion } from 'framer-motion'
import gsap from 'gsap'
import './App.css'
import ParticleField from './ParticleField'
import SmoothScroll from './SmoothScroll'
import CustomCursor from './CustomCursor'
import ScrollProgress from './ScrollProgress'
import MagneticButton from './MagneticButton'
import SplitHeroName from './SplitHeroName'
import useIsDesktop from './useIsDesktop'
import usePrefersReducedMotion from './usePrefersReducedMotion'

const base = import.meta.env.BASE_URL

const techLabels = [
  { text: 'CIRCUITS', top: '7%', left: '6%' },
  { text: 'EMBEDDED SYSTEMS', top: '13%', left: '74%' },
  { text: 'PCB DESIGN', top: '38%', left: '87%' },
  { text: 'SMART GRID', top: '60%', left: '78%' },
  { text: 'POWER ELECTRONICS', top: '85%', left: '38%' },
  { text: 'ELECTRIC VEHICLES', top: '91%', left: '62%' },
]

const skillGroups = [
  {
    title: 'Power Electronics',
    items: ['Buck / SIMO DC-DC Converters', 'PWM Generation', 'PI Closed-Loop Control', 'Power Conversion System Design'],
  },
  {
    title: 'Microcontrollers & Embedded',
    items: ['TI C2000 (F280049C, F28069)', 'STM32F103C8T6', 'Embedded C', 'ADC / DAC', 'ePWM', 'I²C', 'SPI'],
  },
  {
    title: 'PCB Design & Fabrication',
    items: ['KiCad', 'Schematic Capture', 'Multi-layer Layout', 'Power/Ground Planes', 'DRC', 'Gerber / BOM Generation'],
  },
  {
    title: 'Power Systems',
    items: ['Energy Metering', 'CTs / PTs', 'Relays & Circuit Breakers', 'Substation & SCADA Monitoring'],
  },
  {
    title: 'Development Tools',
    items: ['MATLAB / Simulink', 'Code Composer Studio', 'STM32CubeIDE'],
  },
  {
    title: 'Programming Languages',
    items: ['C', 'C++', 'Python'],
  },
]

const projects = [
  {
    title: 'SIMO DC-DC Buck Converter — Design & Simulation',
    tag: 'MATLAB/Simulink',
    meta: 'Design Calculations Lead · Three-member team · SASTRA Deemed to be University · May 2026',
    desc: 'Designed a six-switch, five-inductor Single-Input Multiple-Output buck converter generating regulated 18.5V, 15V, 12V, 5V, and a newly added 3.3V output from a 48V DC input. Performed duty-cycle, inductance, and capacitance calculations for Continuous Conduction Mode with a 0.02% output-ripple target, then built the MATLAB/Simulink model with PI closed-loop control and NAND-based switching logic, verifying voltage, current, PWM, and ripple performance.',
    report: `${base}SIMO_Buck_Converter_Report.pdf`,
  },
  {
    title: 'Synchronous Buck Converter for TT Motor Drive — Embedded Firmware',
    tag: 'TI TMS320F28069 · Code Composer Studio',
    meta: 'SASTRA Deemed to be University · Nov 2025',
    desc: 'Designed and implemented an open-loop synchronous buck converter stepping a 12V DC input down to 5V to drive a DC motor. Developed firmware on a TI TMS320F28069 microcontroller generating complementary PWM signals with deadband through the ePWM module, driving two MOSFETs via an IR gate driver for accurate voltage and speed control.',
    report: `${base}TT_Motor_Drive_C2000_Report.pdf`,
  },
  {
    title: 'LAUNCHXL-F280049C — Four-Layer PCB Design',
    tag: 'KiCad',
    meta: 'SASTRA Deemed to be University',
    desc: 'Designed a four-layer TI C2000 LaunchPad PCB in KiCad with dedicated power/ground planes, component placement, and routing. Performed Design Rule Checks and generated Gerber, drill, and BOM files for fabrication.',
  },
  {
    title: 'STM32F103C8T6 — Two-Layer PCB Design',
    tag: 'KiCad',
    meta: 'SASTRA Deemed to be University',
    desc: 'Designed a two-layer STM32F103C8T6 PCB with schematic capture, ground pour, and routing. Performed Design Rule Checks and generated Gerber files for fabrication.',
  },
]

function Reveal({ children, delay = 0 }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.55, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  )
}

function RevealSide({ children, delay = 0, fromRight = false }) {
  return (
    <motion.div
      initial={{ opacity: 0, x: fromRight ? 40 : -40 }}
      whileInView={{ opacity: 1, x: 0 }}
      viewport={{ once: true, margin: '-80px' }}
      transition={{ duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  )
}

function App() {
  const isDesktop = useIsDesktop()
  const prefersReducedMotion = usePrefersReducedMotion()

  const handleCardMove = (e) => {
    const card = e.currentTarget
    const rect = card.getBoundingClientRect()
    const px = (e.clientX - rect.left) / rect.width
    const py = (e.clientY - rect.top) / rect.height
    card.style.setProperty('--mx', `${px * 100}%`)
    card.style.setProperty('--my', `${py * 100}%`)

    if (!isDesktop || prefersReducedMotion) return
    const rotateY = (px - 0.5) * 14
    const rotateX = (0.5 - py) * 14
    gsap.to(card, {
      rotateX,
      rotateY,
      scale: 1.015,
      transformPerspective: 800,
      duration: 0.4,
      ease: 'power3.out',
    })
  }

  const handleCardLeave = (e) => {
    gsap.to(e.currentTarget, { rotateX: 0, rotateY: 0, scale: 1, duration: 0.6, ease: 'power3.out' })
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

      <div className="site" id="top">
        <header className="hero">
          {techLabels.map((label, i) => (
            <motion.span
              key={label.text}
              className="tech-label"
              style={{ top: label.top, left: label.left }}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 1, delay: 0.9 + i * 0.12 }}
            >
              {label.text}
            </motion.span>
          ))}
          <motion.p
            className="hero-eyebrow-label"
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            EEE STUDENT · ENGINEER · BUILDER
          </motion.p>
          <h1 className="hero-name">
            <SplitHeroName as="span" className="hero-name-plain" text="Arul " />
            <SplitHeroName as="span" className="hero-name-accent" text="Jeffry" delayOffset={0.12} />
          </h1>
          <motion.p
            className="hero-tagline"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.4 }}
          >
            Turning circuits and code into a smarter tomorrow.
          </motion.p>
          <motion.div
            className="hero-actions"
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
            className="hero-actions"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.65 }}
          >
            <MagneticButton className="btn btn-primary" href="#projects">See My Work →</MagneticButton>
            <MagneticButton className="btn btn-secondary" href={`${base}Arul_Jeffry_A_Resume.pdf`} target="_blank" rel="noreferrer">Download Résumé ⬇</MagneticButton>
          </motion.div>

          <motion.div
            className="side-label side-label-right"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1, delay: 1.1 }}
          >
            <span>CURIOSITY</span>
            <span>BUILDS</span>
            <span>DEEPER</span>
            <span>WORLDS</span>
          </motion.div>

          <motion.div
            className="side-label side-label-left"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1, delay: 1.2 }}
          >
            <span>IDEAS</span>
            <span>NEVER</span>
            <span>STOP</span>
          </motion.div>

          <motion.div
            className="scroll-indicator"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.9 }}
          >
            <span className="scroll-ring" />
            SCROLL —
          </motion.div>
        </header>

        <section id="about">
          <Reveal>
            <p className="section-title">About</p>
            <h2 className="section-heading">Background</h2>
            <div className="about">
              <p>
                I'm an Electrical &amp; Electronics Engineering student specializing in Smart Grid
                and Electric Vehicles at SASTRA Deemed to be University, Thanjavur. My work centers
                on DC-DC power conversion, closed-loop control design, and embedded firmware for
                power electronic systems — from duty-cycle and component calculations through to
                MATLAB/Simulink modeling, C2000 firmware, and multi-layer PCB fabrication in KiCad.
                I've also spent time on the power-systems side through an internship covering energy
                metering, protection equipment, and SCADA-based substation monitoring.
              </p>
            </div>
          </Reveal>
        </section>

        <section id="skills">
          <Reveal>
            <p className="section-title">Skills</p>
            <h2 className="section-heading">What I work with</h2>
          </Reveal>
          <div className="skills-grid">
            {skillGroups.map((group, i) => (
              <Reveal key={group.title} delay={i * 0.06}>
                <div className="skill-card">
                  <h3>{group.title}</h3>
                  <div className="chip-row">
                    {group.items.map((item) => (
                      <span className="chip" key={item}>{item}</span>
                    ))}
                  </div>
                </div>
              </Reveal>
            ))}
          </div>
        </section>

        <section id="projects">
          <Reveal>
            <p className="section-title">Projects</p>
            <h2 className="section-heading">Selected work</h2>
          </Reveal>
          <div className="project-list">
            {projects.map((p, i) => (
              <RevealSide key={p.title} delay={i * 0.05} fromRight={i % 2 === 1}>
                <article className="project-card" onMouseMove={handleCardMove} onMouseLeave={handleCardLeave}>
                  <span className="project-number">{String(i + 1).padStart(2, '0')}</span>
                  <div className="project-head">
                    <h3>{p.title}</h3>
                    <span className="project-tag">{p.tag}</span>
                  </div>
                  <p className="project-meta">{p.meta}</p>
                  <p className="desc">{p.desc}</p>
                  {p.report && (
                    <div className="project-links">
                      <a href={p.report} target="_blank" rel="noreferrer">Read full report →</a>
                    </div>
                  )}
                </article>
              </RevealSide>
            ))}
          </div>
        </section>

        <section id="experience">
          <Reveal>
            <p className="section-title">Experience</p>
            <h2 className="section-heading">Internship</h2>
            <div className="timeline-item">
              <h3>Electrical Engineering Intern</h3>
              <span className="org">TANGEDCO — Trichy Electricity Distribution Circle</span>
              <span className="period">Dec 2025</span>
              <ul>
                <li>Studied energy meter types, operating principles, and testing procedures.</li>
                <li>Covered CTs, PTs, transformers, relays, and circuit breakers, including their operating principles and ratings.</li>
                <li>Analyzed substation single-line diagrams and SCADA-based voltage and current monitoring.</li>
              </ul>
            </div>
          </Reveal>
        </section>

        <section id="education">
          <Reveal>
            <p className="section-title">Education</p>
            <h2 className="section-heading">Academics</h2>
            <div className="timeline-item">
              <h3>B.Tech, Electrical &amp; Electronics Engineering (Smart Grid and Electric Vehicles)</h3>
              <span className="org">SASTRA Deemed to be University, Thanjavur</span>
              <span className="period">2023 – 2027</span>
              <ul>
                <li>CGPA: 7.115 / 10 · No standing arrears</li>
              </ul>
            </div>
            <div className="timeline-item">
              <h3>Higher Secondary Certificate (HSC)</h3>
              <span className="org">St. Joseph's College Hr Sec School</span>
              <span className="period">80%</span>
            </div>
          </Reveal>
        </section>

        <section id="certifications">
          <Reveal>
            <p className="section-title">Certifications</p>
            <h2 className="section-heading">Courses &amp; workshops</h2>
            <ul className="cert-list">
              <li>PCB Design Course — MHI Training Centre, SASTRA Deemed to be University</li>
              <li>Introduction to MATLAB and Simulink Workshop</li>
            </ul>
          </Reveal>
        </section>

        <section id="contact">
          <Reveal>
            <p className="section-title">Contact</p>
            <h2 className="section-heading">Get in touch</h2>
            <div className="contact-grid">
              <a className="contact-card" href="mailto:aruljeffry.2005a@gmail.com">
                <span className="label">Email</span>
                <span className="value">aruljeffry.2005a@gmail.com</span>
              </a>
              <a className="contact-card" href="tel:+918754534022">
                <span className="label">Phone</span>
                <span className="value">+91 87545 34022</span>
              </a>
              <a className="contact-card" href="https://www.linkedin.com/in/arul-jeffry-a-3489b7300" target="_blank" rel="noreferrer">
                <span className="label">LinkedIn</span>
                <span className="value">arul-jeffry-a</span>
              </a>
              <div className="contact-card">
                <span className="label">Location</span>
                <span className="value">Tiruchirappalli / Tirunelveli, Tamil Nadu, India</span>
              </div>
            </div>
          </Reveal>
        </section>
      </div>

      <footer>
        © {new Date().getFullYear()} Arul Jeffry A. Built with React &amp; Vite, deployed on GitHub Pages.
      </footer>
    </SmoothScroll>
  )
}

export default App
