export default function GroupNode({ data, style }) {
  const { label, color } = data
  return (
    <div style={{
      width: style?.width, height: style?.height,
      border: `1px solid ${color}22`,
      borderTop: `2px solid ${color}35`,
      borderRadius: 14,
      background: `${color}05`,
      position: 'relative',
      pointerEvents: 'none',
    }}>
      <div style={{
        position: 'absolute', top: 10, left: 14,
        display: 'flex', alignItems: 'center', gap: 5,
      }}>
        <div style={{ width: 5, height: 5, borderRadius: '50%', background: color, opacity: 0.7 }} />
        <span style={{
          fontSize: 9, fontWeight: 700,
          letterSpacing: '0.1em', textTransform: 'uppercase',
          color, opacity: 0.6, whiteSpace: 'nowrap',
        }}>
          {label}
        </span>
      </div>
    </div>
  )
}
