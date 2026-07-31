import { Handle, Position } from '@xyflow/react'

export default function KongNode({ data, selected }) {
  const { plugins = [], upstreams = 0, color } = data

  return (
    <div style={{
      background: 'linear-gradient(145deg, rgba(251,191,36,0.12) 0%, rgba(245,158,11,0.06) 100%)',
      backdropFilter: 'blur(16px)',
      border: `1px solid ${selected ? color : 'rgba(251,191,36,0.3)'}`,
      borderRadius: 12,
      padding: '14px 18px',
      minWidth: 195,
      cursor: 'grab',
      position: 'relative',
      boxShadow: selected
        ? `0 0 0 1px ${color}50, 0 0 40px ${color}30, 0 4px 24px rgba(0,0,0,0.5)`
        : `0 0 24px rgba(251,191,36,0.12), 0 4px 16px rgba(0,0,0,0.4), inset 0 1px 0 rgba(251,191,36,0.1)`,
      transition: 'box-shadow 0.2s',
    }}>

      {/* Icon + title row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <div style={{
          width: 32, height: 32, borderRadius: 8, flexShrink: 0,
          background: 'rgba(251,191,36,0.15)',
          border: '1px solid rgba(251,191,36,0.3)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 16,
        }}>
          ⬡
        </div>
        <div>
          <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: '0.14em', color: '#f59e0b', textTransform: 'uppercase', marginBottom: 1 }}>
            API Gateway
          </div>
          <div style={{ fontSize: 15, fontWeight: 700, color: '#fef3c7', letterSpacing: '-0.01em' }}>
            Kong
          </div>
        </div>
      </div>

      {/* Plugins */}
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 9 }}>
        {plugins.map(p => (
          <span key={p} style={{
            fontSize: 9, padding: '2px 7px',
            background: 'rgba(251,191,36,0.1)',
            border: '1px solid rgba(251,191,36,0.22)',
            borderRadius: 4, color: '#fbbf24',
            fontWeight: 500, letterSpacing: '0.02em',
          }}>
            {p}
          </span>
        ))}
      </div>

      {/* Upstreams count */}
      <div style={{ fontSize: 9, color: '#78716c', letterSpacing: '0.02em' }}>
        {upstreams} upstream services registered
      </div>

      <Handle type="target" position={Position.Left}   style={{ background: '#f59e0b', border: 'none', width: 7, height: 7 }} />
      <Handle type="source" position={Position.Right}  style={{ background: '#f59e0b', border: 'none', width: 7, height: 7 }} />
      <Handle type="target" position={Position.Top}    style={{ background: '#f59e0b', border: 'none', width: 7, height: 7 }} />
      <Handle type="source" position={Position.Bottom} style={{ background: '#f59e0b', border: 'none', width: 7, height: 7 }} />
    </div>
  )
}
