import { Handle, Position } from '@xyflow/react'

const BADGE = {
  personal: 'Personal', itaas: 'ITaaS', cmse: 'CMSE',
  mib: 'MIB', aws: 'AWS', ext: 'External', mgmt: 'Mgmt',
}

export default function ServiceNode({ data, selected }) {
  const { label, sub, color, platform } = data
  const isManaged  = platform === 'aws'
  const isExternal = platform === 'ext'

  return (
    <div style={{
      background: '#ffffff',
      border: `1px solid ${selected ? color : '#e2e8f0'}`,
      borderLeft: `3px solid ${color}`,
      borderRadius: 8,
      padding: '9px 12px',
      minWidth: 158,
      maxWidth: 192,
      cursor: 'grab',
      position: 'relative',
      boxShadow: selected
        ? `0 0 0 2px ${color}28, 0 4px 20px rgba(0,0,0,0.1)`
        : '0 1px 4px rgba(0,0,0,0.07)',
      transition: 'box-shadow 0.15s, border-color 0.15s',
    }}>

      {/* Status dot */}
      {!isExternal && (
        <div style={{
          position: 'absolute', top: 9, right: 9,
          width: 6, height: 6, borderRadius: '50%',
          background: isManaged ? '#f97316' : '#22c55e',
        }} />
      )}

      {/* Badge */}
      <div style={{
        display: 'inline-block', marginBottom: 5,
        fontSize: 8, fontWeight: 700,
        letterSpacing: '0.1em', textTransform: 'uppercase',
        color, background: `${color}12`,
        border: `1px solid ${color}25`,
        borderRadius: 3, padding: '1px 5px',
      }}>
        {BADGE[platform] ?? platform}
      </div>

      {/* Name */}
      <div style={{ fontSize: 12, fontWeight: 600, color: '#0f172a', lineHeight: 1.3, marginBottom: 3 }}>
        {label}
      </div>

      {/* Sub */}
      <div style={{ fontSize: 9, color: '#94a3b8', lineHeight: 1.45, whiteSpace: 'pre-wrap' }}>
        {sub}
      </div>

      <Handle type="target" position={Position.Left}   style={{ background: color, border: '2px solid white', width: 8, height: 8 }} />
      <Handle type="source" position={Position.Right}  style={{ background: color, border: '2px solid white', width: 8, height: 8 }} />
      <Handle type="target" position={Position.Top}    style={{ background: color, border: '2px solid white', width: 8, height: 8 }} />
      <Handle type="source" position={Position.Bottom} style={{ background: color, border: '2px solid white', width: 8, height: 8 }} />
    </div>
  )
}
