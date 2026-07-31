import { Handle, Position } from '@xyflow/react'

const PLATFORM_BADGE = {
  personal: 'Personal',
  itaas:    'ITaaS',
  cmse:     'CMSE',
  mib:      'MIB',
  aws:      'AWS',
  ext:      'External',
}

export default function ServiceNode({ data, selected }) {
  const { label, sub, color, platform } = data
  const isExternal = platform === 'ext'
  const isAws      = platform === 'aws'
  const isLive     = !isExternal

  return (
    <div style={{
      background: '#ffffff',
      border: `1.5px solid ${selected ? color : '#e2e8f0'}`,
      borderLeft: `4px solid ${color}`,
      borderRadius: 8,
      padding: '8px 12px',
      minWidth: 148,
      maxWidth: 190,
      boxShadow: selected
        ? `0 0 0 2px ${color}33, 0 4px 16px ${color}22`
        : '0 1px 4px rgba(0,0,0,0.08)',
      cursor: 'grab',
      position: 'relative',
    }}>
      {/* Live dot */}
      {isLive && (
        <span style={{
          position: 'absolute', top: 8, right: 8,
          width: 6, height: 6,
          borderRadius: '50%',
          background: isAws ? '#f59e0b' : '#22c55e',
          boxShadow: `0 0 0 2px ${isAws ? '#fef3c7' : '#dcfce7'}`,
        }} />
      )}

      {/* Platform badge */}
      <div style={{
        display: 'inline-block',
        fontSize: 8,
        fontWeight: 600,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        color,
        background: `${color}12`,
        borderRadius: 3,
        padding: '1px 5px',
        marginBottom: 4,
      }}>
        {PLATFORM_BADGE[platform] ?? platform}
      </div>

      {/* Service name */}
      <div style={{
        fontSize: 12,
        fontWeight: 600,
        color: '#0f172a',
        lineHeight: 1.3,
        marginBottom: 3,
      }}>
        {label}
      </div>

      {/* Sublabel */}
      <div style={{
        fontSize: 9,
        color: '#94a3b8',
        lineHeight: 1.4,
        whiteSpace: 'pre-wrap',
      }}>
        {sub}
      </div>

      <Handle type="target" position={Position.Left}  style={{ background: color, border: 'none', width: 6, height: 6 }} />
      <Handle type="source" position={Position.Right} style={{ background: color, border: 'none', width: 6, height: 6 }} />
      <Handle type="target" position={Position.Top}    style={{ background: color, border: 'none', width: 6, height: 6 }} />
      <Handle type="source" position={Position.Bottom} style={{ background: color, border: 'none', width: 6, height: 6 }} />
    </div>
  )
}
