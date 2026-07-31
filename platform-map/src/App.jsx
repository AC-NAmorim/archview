import { useCallback } from 'react'
import {
  ReactFlow, Background, Controls, MiniMap,
  useNodesState, useEdgesState, addEdge,
  BackgroundVariant,
} from '@xyflow/react'
import { initialNodes, initialEdges, COLORS } from './data.js'
import GroupNode   from './GroupNode.jsx'
import ServiceNode from './ServiceNode.jsx'
import KongNode    from './KongNode.jsx'

const nodeTypes = { groupNode: GroupNode, serviceNode: ServiceNode, kongNode: KongNode }

const LEGEND_PLATFORMS = [
  { label: 'Personal Platform',     color: COLORS.personal },
  { label: 'Kong · API Gateway',    color: COLORS.kong     },
  { label: 'ITaaS Shared Services', color: COLORS.itaas    },
  { label: 'CMSE Content Pipeline', color: COLORS.cmse     },
  { label: 'MIB / DMM CMS',         color: COLORS.mib      },
  { label: 'AWS Managed',           color: COLORS.aws      },
  { label: 'External BSS/Partner',  color: COLORS.ext      },
  { label: 'Management Portal',     color: COLORS.mgmt     },
]

const LEGEND_EDGES = [
  { label: 'REST / JSON',  color: '#475569', dash: false  },
  { label: 'via Kong',     color: '#f59e0b', dash: false  },
  { label: 'SOAP / XML',   color: '#ef4444', dash: true   },
  { label: 'OIDC / JWT',   color: '#8b5cf6', dash: true   },
  { label: 'AWS SDK',      color: '#f97316', dash: false  },
]

export default function App() {
  const [nodes, , onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)
  const onConnect = useCallback(p => setEdges(es => addEdge(p, es)), [setEdges])

  const minimapColor = n => COLORS[n.data?.platform] ?? '#1e293b'

  // Live service count (non-ext, non-group nodes)
  const liveCount = initialNodes.filter(n => n.type === 'serviceNode' && !['ext'].includes(n.data?.platform)).length

  return (
    <div style={{ width: '100vw', height: '100vh', background: '#07090f' }}>
      <ReactFlow
        nodes={nodes} edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        nodeTypes={nodeTypes}
        fitView fitViewOptions={{ padding: 0.1 }}
        minZoom={0.15} maxZoom={2.2}
        proOptions={{ hideAttribution: false }}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={24} size={1}
          color="rgba(99,102,241,0.12)"
        />
        <Controls className="dark-controls" />
        <MiniMap
          nodeColor={minimapColor}
          maskColor="rgba(7,9,15,0.75)"
          style={{
            background: '#0c1020',
            border: '1px solid rgba(255,255,255,0.07)',
            borderRadius: 10,
          }}
        />
      </ReactFlow>

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div style={{
        position: 'absolute', top: 18, left: '50%', transform: 'translateX(-50%)',
        background: 'rgba(10,14,26,0.9)',
        backdropFilter: 'blur(20px)',
        border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: 12,
        padding: '10px 24px',
        textAlign: 'center',
        pointerEvents: 'none',
        boxShadow: '0 4px 32px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.06)',
      }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: '#e2e8f0', letterSpacing: '0.04em' }}>
          AgileTV · Platform Architecture
        </div>
        <div style={{ fontSize: 10, color: '#334155', marginTop: 3, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
          Confirmed production topology
        </div>
      </div>

      {/* ── Status bar ──────────────────────────────────────────────────── */}
      <div style={{
        position: 'absolute', top: 18, right: 18,
        background: 'rgba(10,14,26,0.9)',
        backdropFilter: 'blur(20px)',
        border: '1px solid rgba(255,255,255,0.07)',
        borderRadius: 12,
        padding: '10px 16px',
        boxShadow: '0 4px 24px rgba(0,0,0,0.4)',
        display: 'flex', flexDirection: 'column', gap: 5,
      }}>
        {[
          { label: 'ECS Services',  value: `${liveCount} live` },
          { label: 'AWS Accounts',  value: '469793732550 · 211125718407' },
          { label: 'Regions',       value: 'us-east-1 · eu-west-1' },
          { label: 'API Gateway',   value: 'Kong · key-auth + ACL' },
          { label: 'IAM',           value: 'Keycloak · Telecom SSO · Swordfish' },
          { label: 'CI/CD',         value: 'Travis CI · TeamCity' },
        ].map(({ label, value }) => (
          <div key={label} style={{ display: 'flex', justifyContent: 'space-between', gap: 20 }}>
            <span style={{ fontSize: 10, color: '#334155', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</span>
            <span style={{ fontSize: 10, color: '#60a5fa', fontWeight: 600 }}>{value}</span>
          </div>
        ))}
      </div>

      {/* ── Legend ──────────────────────────────────────────────────────── */}
      <div style={{
        position: 'absolute', bottom: 18, left: 18,
        background: 'rgba(10,14,26,0.9)',
        backdropFilter: 'blur(20px)',
        border: '1px solid rgba(255,255,255,0.07)',
        borderRadius: 12,
        padding: '14px 18px',
        boxShadow: '0 4px 24px rgba(0,0,0,0.4)',
        display: 'flex', gap: 28,
      }}>
        <div>
          <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#1e293b', marginBottom: 9 }}>Platform</div>
          {LEGEND_PLATFORMS.map(({ label, color }) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 6 }}>
              <div style={{ width: 8, height: 8, borderRadius: 2, background: color, boxShadow: `0 0 4px ${color}80`, flexShrink: 0 }} />
              <span style={{ fontSize: 10, color: '#475569' }}>{label}</span>
            </div>
          ))}
        </div>

        <div>
          <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#1e293b', marginBottom: 9 }}>Interface</div>
          {LEGEND_EDGES.map(({ label, color, dash }) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 6 }}>
              <svg width="22" height="6" style={{ flexShrink: 0 }}>
                <line x1="0" y1="3" x2="22" y2="3" stroke={color} strokeWidth="1.5"
                  strokeDasharray={dash ? '4 3' : undefined} />
              </svg>
              <span style={{ fontSize: 10, color: '#475569' }}>{label}</span>
            </div>
          ))}
          <div style={{ marginTop: 10, borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: 9 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5 }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#22c55e', boxShadow: '0 0 5px #22c55e', flexShrink: 0 }} />
              <span style={{ fontSize: 10, color: '#475569' }}>ECS service · running</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#f97316', boxShadow: '0 0 5px #f97316', flexShrink: 0 }} />
              <span style={{ fontSize: 10, color: '#475569' }}>AWS managed resource</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
