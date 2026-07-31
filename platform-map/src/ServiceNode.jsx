import { Handle, Position } from '@xyflow/react'

const BADGE = {
  personal: 'Personal', itaas: 'ITaaS', cmse: 'CMSE',
  mib: 'MIB', aws: 'AWS', ext: 'External', mgmt: 'Mgmt',
}

export default function ServiceNode({ data, selected }) {
  const { label, sub, color, platform } = data
  const isLive    = !['ext'].includes(platform)
  const isManaged = platform === 'aws'

  return (
    <div style={{
      background: 'rgba(10,14,26,0.85)',
      backdropFilter: 'blur(16px)',
      border: `1px solid ${selected ? color : 'rgba(255,255,255,0.07)'}`,
      borderLeft: `3px solid ${color}`,
      borderRadius: 8,
      padding: '9px 13px',
      minWidth: 155,
      maxWidth: 195,
      cursor: 'grab',
      position: 'relative',
      boxShadow: selected
        ? `0 0 0 1px ${color}40, 0 4px 24px ${color}28, inset 0 1px 0 rgba(255,255,255,0.05)`
        : `0 2px 12px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.04)`,
      transition: 'box-shadow 0.2s, border-color 0.2s',
    }}>

      {/* Status indicator */}
      {isLive && (
        <div style={{
          position: 'absolute', top: 9, right: 10,
          width: 6, height: 6, borderRadius: '50%',
          background: isManaged ? '#f97316' : '#22c55e',
          boxShadow: isManaged
            ? '0 0 6px #f97316, 0 0 2px #f97316'
            : '0 0 6px #22c55e, 0 0 2px #22c55e',
        }} />
      )}

      {/* Platform badge */}
      <div style={{
        display: 'inline-block',
        fontSize: 8, fontWeight: 700,
        letterSpacing: '0.1em', textTransform: 'uppercase',
        color, background: `${color}18`,
        border: `1px solid ${color}28`,
        borderRadius: 3, padding: '1px 5px', marginBottom: 5,
      }}>
        {BADGE[platform] ?? platform}
      </div>

      {/* Service name */}
      <div style={{
        fontSize: 12, fontWeight: 600,
        color: '#e2e8f0', lineHeight: 1.3, marginBottom: 3,
      }}>
        {label}
      </div>

      {/* Sub-label */}
      <div style={{
        fontSize: 9, color: '#475569',
        lineHeight: 1.45, whiteSpace: 'pre-wrap',
      }}>
        {sub}
      </div>

      <Handle type="target" position={Position.Left}   style={{ background: color, border: 'none', width: 5, height: 5, opacity: 0.7 }} />
      <Handle type="source" position={Position.Right}  style={{ background: color, border: 'none', width: 5, height: 5, opacity: 0.7 }} />
      <Handle type="target" position={Position.Top}    style={{ background: color, border: 'none', width: 5, height: 5, opacity: 0.7 }} />
      <Handle type="source" position={Position.Bottom} style={{ background: color, border: 'none', width: 5, height: 5, opacity: 0.7 }} />
    </div>
  )
}
