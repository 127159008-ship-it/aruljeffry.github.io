const lines = [
  { top: '14%', left: '4%', width: '18%', dot: 'right' },
  { top: '14%', left: '78%', width: '18%', dot: 'left' },
  { top: '34%', left: '84%', width: '14%', dot: 'left' },
  { top: '62%', left: '2%', width: '16%', dot: 'right' },
  { top: '80%', left: '70%', width: '20%', dot: 'left' },
]

const verticals = [
  { left: '22%', top: '10%', height: '20%' },
  { left: '58%', top: '8%', height: '28%' },
  { left: '86%', top: '30%', height: '18%' },
  { left: '12%', top: '58%', height: '16%' },
  { left: '92%', top: '66%', height: '20%' },
]

export default function GridLines() {
  return (
    <div className="grid-lines" aria-hidden="true">
      {lines.map((l, i) => (
        <span
          key={`h-${i}`}
          className={`grid-line horizontal dot-${l.dot}`}
          style={{ top: l.top, left: l.left, width: l.width }}
        />
      ))}
      {verticals.map((l, i) => (
        <span
          key={`v-${i}`}
          className="grid-line vertical"
          style={{ left: l.left, top: l.top, height: l.height }}
        />
      ))}
    </div>
  )
}
