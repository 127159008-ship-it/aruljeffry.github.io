const base = import.meta.env.BASE_URL

export const skillGroups = [
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

export const projects = [
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

export const timeline = [
  {
    kind: 'Experience',
    title: 'Electrical Engineering Intern',
    org: 'TANGEDCO — Trichy Electricity Distribution Circle',
    period: 'Dec 2025',
    points: [
      'Studied energy meter types, operating principles, and testing procedures.',
      'Covered CTs, PTs, transformers, relays, and circuit breakers, including their operating principles and ratings.',
      'Analyzed substation single-line diagrams and SCADA-based voltage and current monitoring.',
    ],
  },
  {
    kind: 'Education',
    title: 'B.Tech, Electrical & Electronics Engineering (Smart Grid and Electric Vehicles)',
    org: 'SASTRA Deemed to be University, Thanjavur',
    period: '2023 – 2027',
    points: ['CGPA: 7.115 / 10 · No standing arrears'],
  },
  {
    kind: 'Education',
    title: 'Higher Secondary Certificate (HSC)',
    org: "St. Joseph's College Hr Sec School",
    period: '80%',
    points: [],
  },
]

export const certifications = [
  'PCB Design Course — MHI Training Centre, SASTRA Deemed to be University',
  'Introduction to MATLAB and Simulink Workshop',
]

export const contactLinks = [
  { label: 'Email', value: 'aruljeffry.2005a@gmail.com', href: 'mailto:aruljeffry.2005a@gmail.com' },
  { label: 'Phone', value: '+91 87545 34022', href: 'tel:+918754534022' },
  { label: 'LinkedIn', value: 'arul-jeffry-a', href: 'https://www.linkedin.com/in/arul-jeffry-a-3489b7300' },
  { label: 'Location', value: 'Tiruchirappalli / Tirunelveli, Tamil Nadu, India', href: null },
]

export const resumeUrl = `${base}Arul_Jeffry_A_Resume.pdf`

export const stats = [
  { value: '2027', label: 'Graduation Year' },
  { value: '7.11', label: 'CGPA / 10' },
  { value: '4+', label: 'Engineering Projects' },
  { value: '1', label: 'Industry Internship' },
]
