// Purely decorative background node — no handles, just a labelled region.
export default function GroupNode({ data, style }) {
  const { label, color } = data
  return (
    <div style={{
      width: style?.width, height: style?.height,
      border: `1px solid ${color}30`,
      borderRadius: 14,
      background: `${color}06`,
      position: 'relative',
      pointerEvents: 'none',
    }}>
      <span style={{
        position: 'absolute',
        top: 10, left: 14,
        fontSize: 9,
        fontWeight: 600,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        color,
        opacity: 0.6,
        whiteSpace: 'nowrap',
      }}>
        {label}
      </span>
    </div>
  )
}
