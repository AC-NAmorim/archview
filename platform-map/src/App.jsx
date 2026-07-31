import { useCallback, useState } from 'react'
import {
  ReactFlow, ReactFlowProvider, Background, Controls, MiniMap,
  useNodesState, useEdgesState, addEdge, useReactFlow,
  BackgroundVariant,
} from '@xyflow/react'
import { initialNodes, initialEdges, COLORS } from './data.js'
import { applyDagreLayout } from './layout.js'
import GroupNode   from './GroupNode.jsx'
import ServiceNode from './ServiceNode.jsx'
import KongNode    from './KongNode.jsx'

const nodeTypes = { groupNode: GroupNode, serviceNode: ServiceNode, kongNode: KongNode }

// ── Layout direction options ────────────────────────────────────────────────
const DIRECTIONS = [
  { id: 'LR', label: '→', title: 'Left → Right' },
  { id: 'TB', label: '↓', title: 'Top → Bottom'  },
  { id: 'RL', label: '←', title: 'Right → Left'  },
  { id: 'BT', label: '↑', title: 'Bottom → Top'  },
]

// ── Legend data ─────────────────────────────────────────────────────────────
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
  { label: 'REST / JSON', color: '#94a3b8', dash: false },
  { label: 'via Kong',    color: COLORS.kong, dash: false },
  { label: 'SOAP / XML',  color: COLORS.ext,  dash: true  },
  { label: 'OIDC / JWT',  color: COLORS.itaas, dash: true },
  { label: 'AWS SDK',     color: COLORS.aws,  dash: false },
]

// ── Inner map component (needs ReactFlowProvider ancestor) ──────────────────
function PlatformMap() {
  const { fitView } = useReactFlow()
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)
  const [activeDir, setActiveDir] = useState(null) // null = manual

  const onConnect = useCallback(p => setEdges(es => addEdge(p, es)), [setEdges])

  const runLayout = useCallback((dir) => {
    setActiveDir(dir)
    const laid = applyDagreLayout(nodes, edges, dir)
    setNodes(laid)
    setTimeout(() => fitView({ padding: 0.12, duration: 550 }), 20)
  }, [nodes, edges, setNodes, fitView])

  const resetLayout = useCallback(() => {
    setActiveDir(null)
    setNodes(initialNodes)
    setTimeout(() => fitView({ padding: 0.12, duration: 400 }), 20)
  }, [setNodes, fitView])

  const liveCount = initialNodes.filter(
    n => n.type === 'serviceNode' && n.data?.platform !== 'ext'
  ).length

  const miniMapColor = n => COLORS[n.data?.platform] ?? '#cbd5e1'

  return (
    <div style={{ width: '100vw', height: '100vh', background: '#f8fafc' }}>
      <ReactFlow
        nodes={nodes} edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        nodeTypes={nodeTypes}
        fitView fitViewOptions={{ padding: 0.12 }}
        minZoom={0.15} maxZoom={2.5}
        proOptions={{ hideAttribution: false }}
      >
        <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#e2e8f0" />
        <Controls />
        <MiniMap
          nodeColor={miniMapColor}
          maskColor="rgba(248,250,252,0.75)"
          style={{ border: '1px solid #e2e8f0', borderRadius: 10 }}
        />
      </ReactFlow>

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div style={{
        position: 'absolute', top: 16, left: '50%', transform: 'translateX(-50%)',
        background: '#ffffff',
        border: '1px solid #e2e8f0',
        borderRadius: 12, padding: '9px 22px',
        textAlign: 'center', pointerEvents: 'none',
        boxShadow: '0 1px 8px rgba(0,0,0,0.07)',
      }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: '#0f172a', letterSpacing: '0.02em' }}>
          AgileTV · Platform Architecture
        </div>
        <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 2, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
          Confirmed production topology · {liveCount} services
        </div>
      </div>

      {/* ── Layout toolbar ──────────────────────────────────────────────── */}
      <div style={{
        position: 'absolute', top: 76, left: '50%', transform: 'translateX(-50%)',
        display: 'flex', alignItems: 'center', gap: 6,
        background: '#ffffff',
        border: '1px solid #e2e8f0',
        borderRadius: 10, padding: '6px 10px',
        boxShadow: '0 1px 6px rgba(0,0,0,0.07)',
      }}>
        <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#94a3b8', marginRight: 4 }}>
          Auto Layout
        </span>

        {DIRECTIONS.map(({ id, label, title }) => (
          <button key={id} title={title} onClick={() => runLayout(id)} style={{
            width: 32, height: 28,
            borderRadius: 6, border: '1px solid',
            fontSize: 13, fontWeight: 600,
            cursor: 'pointer', transition: 'all 0.15s',
            background: activeDir === id ? '#2563eb' : '#f8fafc',
            color: activeDir === id ? '#ffffff' : '#64748b',
            borderColor: activeDir === id ? '#2563eb' : '#e2e8f0',
          }}>
            {label}
          </button>
        ))}

        <div style={{ width: 1, height: 18, background: '#e2e8f0', margin: '0 2px' }} />

        <button onClick={resetLayout} title="Reset to manual layout" style={{
          padding: '0 10px', height: 28,
          borderRadius: 6, border: '1px solid #e2e8f0',
          fontSize: 10, fontWeight: 600, letterSpacing: '0.04em',
          cursor: 'pointer', background: '#f8fafc', color: '#64748b',
          transition: 'all 0.15s',
        }}>
          Reset
        </button>

        {activeDir && (
          <span style={{ fontSize: 9, color: '#94a3b8', marginLeft: 2 }}>
            Groups hidden during auto-layout · drag to rearrange
          </span>
        )}
      </div>

      {/* ── Status panel ────────────────────────────────────────────────── */}
      <div style={{
        position: 'absolute', top: 16, right: 16,
        background: '#ffffff', border: '1px solid #e2e8f0',
        borderRadius: 12, padding: '11px 16px',
        boxShadow: '0 1px 8px rgba(0,0,0,0.07)',
        display: 'flex', flexDirection: 'column', gap: 5,
        minWidth: 260,
      }}>
        {[
          { label: 'ECS Services',  value: `${liveCount} live` },
          { label: 'Regions',       value: 'us-east-1 · eu-west-1' },
          { label: 'API Gateway',   value: 'Kong · key-auth + ACL' },
          { label: 'IAM',           value: 'Keycloak · Telecom SSO · Swordfish' },
          { label: 'CI / CD',       value: 'Travis CI · TeamCity' },
          { label: 'IaC',           value: 'Terraform 0.13 · AWS ECS Fargate' },
        ].map(({ label, value }) => (
          <div key={label} style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
            <span style={{ fontSize: 10, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</span>
            <span style={{ fontSize: 10, color: '#0f172a', fontWeight: 600 }}>{value}</span>
          </div>
        ))}
      </div>

      {/* ── Legend ──────────────────────────────────────────────────────── */}
      <div style={{
        position: 'absolute', bottom: 16, left: 16,
        background: '#ffffff', border: '1px solid #e2e8f0',
        borderRadius: 12, padding: '12px 16px',
        boxShadow: '0 1px 8px rgba(0,0,0,0.07)',
        display: 'flex', gap: 24,
      }}>
        <div>
          <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#94a3b8', marginBottom: 8 }}>Platform</div>
          {LEGEND_PLATFORMS.map(({ label, color }) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5 }}>
              <div style={{ width: 8, height: 8, borderRadius: 2, background: color, flexShrink: 0 }} />
              <span style={{ fontSize: 10, color: '#475569' }}>{label}</span>
            </div>
          ))}
        </div>

        <div>
          <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#94a3b8', marginBottom: 8 }}>Interface</div>
          {LEGEND_EDGES.map(({ label, color, dash }) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5 }}>
              <svg width="22" height="6" style={{ flexShrink: 0 }}>
                <line x1="0" y1="3" x2="22" y2="3"
                  stroke={color} strokeWidth="1.5"
                  strokeDasharray={dash ? '4 3' : undefined} />
              </svg>
              <span style={{ fontSize: 10, color: '#475569' }}>{label}</span>
            </div>
          ))}

          <div style={{ borderTop: '1px solid #f1f5f9', marginTop: 9, paddingTop: 8 }}>
            {[
              { color: '#22c55e', label: 'ECS service · running' },
              { color: '#f97316', label: 'AWS managed resource' },
            ].map(({ color, label }) => (
              <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 4 }}>
                <div style={{ width: 6, height: 6, borderRadius: '50%', background: color, flexShrink: 0 }} />
                <span style={{ fontSize: 10, color: '#475569' }}>{label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Root — wraps with provider so useReactFlow works ───────────────────────
export default function App() {
  return (
    <ReactFlowProvider>
      <PlatformMap />
    </ReactFlowProvider>
  )
}
