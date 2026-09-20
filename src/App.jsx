import './App.css'

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
    report: '/SIMO_Buck_Converter_Report.pdf',
  },
  {
    title: 'Synchronous Buck Converter for TT Motor Drive — Embedded Firmware',
    tag: 'TI TMS320F28069 · Code Composer Studio',
    meta: 'SASTRA Deemed to be University · Nov 2025',
    desc: 'Designed and implemented an open-loop synchronous buck converter stepping a 12V DC input down to 5V to drive a DC motor. Developed firmware on a TI TMS320F28069 microcontroller generating complementary PWM signals with deadband through the ePWM module, driving two MOSFETs via an IR gate driver for accurate voltage and speed control.',
    report: '/TT_Motor_Drive_C2000_Report.pdf',
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

function App() {
  return (
    <>
      <nav className="nav">
        <div className="nav-inner">
          <a className="nav-name" href="#top">Arul Jeffry A</a>
          <ul className="nav-links">
            <li><a href="#about">About</a></li>
            <li><a href="#skills">Skills</a></li>
            <li><a href="#projects">Projects</a></li>
            <li><a href="#experience">Experience</a></li>
            <li><a href="#contact">Contact</a></li>
          </ul>
        </div>
      </nav>

      <div className="site" id="top">
        <header className="hero">
          <p className="hero-eyebrow">// Electrical &amp; Electronics Engineering</p>
          <h1>Power electronics, embedded control, and PCB design.</h1>
          <p>
            Final-year EEE undergraduate (2027 batch, SASTRA Deemed University) with hands-on
            experience in power conversion, closed-loop control, multi-layer PCB design in KiCad,
            and embedded firmware on TI C2000 microcontrollers. Looking for a Graduate Engineer
            Trainee / Project Engineer role in power conversion, circuit design, and embedded
            control for industrial and electrification applications.
          </p>
          <div className="hero-actions">
            <a className="btn btn-primary" href="#projects">View projects</a>
            <a className="btn btn-secondary" href="/Arul_Jeffry_A_Resume.pdf" target="_blank" rel="noreferrer">Download résumé</a>
          </div>
        </header>

        <section id="about">
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
        </section>

        <section id="skills">
          <p className="section-title">Skills</p>
          <h2 className="section-heading">What I work with</h2>
          <div className="skills-grid">
            {skillGroups.map((group) => (
              <div className="skill-card" key={group.title}>
                <h3>{group.title}</h3>
                <div className="chip-row">
                  {group.items.map((item) => (
                    <span className="chip" key={item}>{item}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section id="projects">
          <p className="section-title">Projects</p>
          <h2 className="section-heading">Selected work</h2>
          <div className="project-list">
            {projects.map((p) => (
              <article className="project-card" key={p.title}>
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
            ))}
          </div>
        </section>

        <section id="experience">
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
        </section>

        <section id="education">
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
        </section>

        <section id="certifications">
          <p className="section-title">Certifications</p>
          <h2 className="section-heading">Courses &amp; workshops</h2>
          <ul className="cert-list">
            <li>PCB Design Course — MHI Training Centre, SASTRA Deemed to be University</li>
            <li>Introduction to MATLAB and Simulink Workshop</li>
          </ul>
        </section>

        <section id="contact">
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
        </section>
      </div>

      <footer>
        © {new Date().getFullYear()} Arul Jeffry A. Built with React &amp; Vite, deployed on GitHub Pages.
      </footer>
    </>
  )
}

export default App
