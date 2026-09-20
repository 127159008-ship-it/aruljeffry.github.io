const traces = [
  'M 2 12 H 22 V 4 H 40',
  'M 0 24 H 14 V 32 H 30 V 20 H 55',
  'M 96 8 H 78 V 18 H 60',
  'M 100 30 H 84 V 40 H 68 V 26',
  'M 4 55 H 20 V 46 H 38 V 60',
  'M 0 72 H 16 V 82 H 34',
  'M 96 60 H 80 V 50 H 64',
  'M 100 82 H 86 V 74 H 66 V 90',
  'M 10 96 V 84 H 28 V 92 H 46',
  'M 60 98 V 88 H 78 V 96',
  'M 46 2 V 12 H 58',
  'M 88 96 V 86 H 72',
]

const vias = [
  [22, 12], [40, 4], [14, 24], [30, 32], [55, 20],
  [78, 8], [60, 18], [84, 30], [68, 40], [20, 55],
  [38, 46], [16, 72], [34, 82], [80, 60], [64, 50],
  [86, 82], [66, 74], [28, 96], [46, 92], [78, 98],
  [58, 2], [88, 86],
]

export default function GridLines() {
  return (
    <div className="grid-lines" aria-hidden="true">
      <svg
        className="circuit-svg"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        {traces.map((d, i) => (
          <path key={i} d={d} className="circuit-trace" vectorEffect="non-scaling-stroke" />
        ))}
        {vias.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="0.45" className="circuit-via" />
        ))}
      </svg>
    </div>
  )
}
