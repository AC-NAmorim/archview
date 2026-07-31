export default function GroupNode({ data, style }) {
  const { label, color } = data
  return (
    <div style={{
      width: style?.width, height: style?.height,
      border: `1px solid ${color}22`,
      borderTop: `1px solid ${color}35`,
      borderRadius: 14,
      background: `linear-gradient(160deg, ${color}07 0%, ${color}03 100%)`,
      backdropFilter: 'blur(4px)',
      position: 'relative',
      pointerEvents: 'none',
      boxShadow: `inset 0 1px 0 ${color}15`,
    }}>
      <div style={{
        position: 'absolute', top: 10, left: 14,
        display: 'flex', alignItems: 'center', gap: 6,
      }}>
        <div style={{
          width: 4, height: 4, borderRadius: '50%',
          background: color, opacity: 0.6,
          boxShadow: `0 0 4px ${color}`,
        }} />
        <span style={{
          fontSize: 9, fontWeight: 700,
          letterSpacing: '0.1em', textTransform: 'uppercase',
          color, opacity: 0.55, whiteSpace: 'nowrap',
        }}>
          {label}
        </span>
      </div>
    </div>
  )
}
