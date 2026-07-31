import { Handle, Position } from '@xyflow/react'

export default function KongNode({ data, selected }) {
  const { plugins = [], upstreams = 0, color } = data

  return (
    <div style={{
      background: '#fffbeb',
      border: `1.5px solid ${selected ? color : '#fde68a'}`,
      borderRadius: 12,
      padding: '13px 16px',
      minWidth: 200,
      cursor: 'grab',
      position: 'relative',
      boxShadow: selected
        ? `0 0 0 3px ${color}22, 0 4px 20px rgba(0,0,0,0.1)`
        : '0 2px 8px rgba(217,119,6,0.12), 0 1px 3px rgba(0,0,0,0.06)',
      transition: 'box-shadow 0.15s, border-color 0.15s',
    }}>

      {/* Icon + title */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 9 }}>
        <div style={{
          width: 30, height: 30, borderRadius: 7, flexShrink: 0,
          background: '#fef3c7', border: '1.5px solid #fde68a',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 15,
        }}>
          ⬡
        </div>
        <div>
          <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: '0.12em', color, textTransform: 'uppercase', marginBottom: 1 }}>
            API Gateway
          </div>
          <div style={{ fontSize: 14, fontWeight: 700, color: '#92400e', letterSpacing: '-0.01em' }}>
            Kong
          </div>
        </div>
      </div>

      {/* Plugin chips */}
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 8 }}>
        {plugins.map(p => (
          <span key={p} style={{
            fontSize: 9, padding: '2px 6px',
            background: '#fef9c3', border: '1px solid #fde68a',
            borderRadius: 4, color: '#92400e', fontWeight: 500,
          }}>
            {p}
          </span>
        ))}
      </div>

      <div style={{ fontSize: 9, color: '#a16207' }}>
        {upstreams} upstream services registered
      </div>

      <Handle type="target" position={Position.Left}   style={{ background: color, border: '2px solid white', width: 9, height: 9 }} />
      <Handle type="source" position={Position.Right}  style={{ background: color, border: '2px solid white', width: 9, height: 9 }} />
      <Handle type="target" position={Position.Top}    style={{ background: color, border: '2px solid white', width: 9, height: 9 }} />
      <Handle type="source" position={Position.Bottom} style={{ background: color, border: '2px solid white', width: 9, height: 9 }} />
    </div>
  )
}
