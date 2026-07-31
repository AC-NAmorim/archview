import { useCallback, useMemo } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  BackgroundVariant,
} from '@xyflow/react'
import { initialNodes, initialEdges, COLORS } from './data.js'
import GroupNode   from './GroupNode.jsx'
import ServiceNode from './ServiceNode.jsx'

const nodeTypes = {
  groupNode:   GroupNode,
  serviceNode: ServiceNode,
}

const LEGEND = [
  { label: 'Personal Platform',    color: COLORS.personal },
  { label: 'ITaaS Shared',         color: COLORS.itaas    },
  { label: 'CMSE Content Pipeline',color: COLORS.cmse     },
  { label: 'MIB / DMM CMS',        color: COLORS.mib      },
  { label: 'AWS Managed',          color: COLORS.aws      },
  { label: 'External BSS/Partner', color: COLORS.ext      },
]

const EDGE_LEGEND = [
  { label: 'REST / JSON',  style: { borderTop: '2px solid #94a3b8' } },
  { label: 'SOAP / XML',   style: { borderTop: '2px dashed #dc2626' } },
  { label: 'OIDC / JWT',   style: { borderTop: '2px dashed #7c3aed' } },
  { label: 'AWS SDK',      style: { borderTop: '2px solid #d97706' } },
]

export default function App() {
  const [nodes, , onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  const onConnect = useCallback(
    (params) => setEdges((eds) => addEdge(params, eds)),
    [setEdges],
  )

  const minimapNodeColor = useCallback((n) => {
    return COLORS[n.data?.platform] ?? '#cbd5e1'
  }, [])

  return (
    <div style={{ width: '100vw', height: '100vh', background: '#f8fafc' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.12 }}
        minZoom={0.2}
        maxZoom={2}
        defaultEdgeOptions={{ type: 'smoothstep' }}
        proOptions={{ hideAttribution: false }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#e2e8f0" />
        <Controls style={{ boxShadow: '0 1px 6px rgba(0,0,0,0.1)', borderRadius: 8 }} />
        <MiniMap
          nodeColor={minimapNodeColor}
          maskColor="rgba(248,250,252,0.7)"
          style={{ border: '1px solid #e2e8f0', borderRadius: 8 }}
        />
      </ReactFlow>

      {/* Header */}
      <div style={{
        position: 'absolute', top: 16, left: '50%', transform: 'translateX(-50%)',
        background: '#ffffff', borderRadius: 10,
        border: '1px solid #e2e8f0',
        padding: '8px 20px',
        boxShadow: '0 1px 6px rgba(0,0,0,0.08)',
        textAlign: 'center',
        pointerEvents: 'none',
      }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: '#0f172a', letterSpacing: '0.02em' }}>
          AgileTV — Platform Service Map
        </div>
        <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 2 }}>
          Confirmed production topology · Drag nodes to rearrange
        </div>
      </div>

      {/* Legend */}
      <div style={{
        position: 'absolute', bottom: 16, left: 16,
        background: '#ffffff',
        border: '1px solid #e2e8f0',
        borderRadius: 10,
        padding: '12px 16px',
        boxShadow: '0 1px 6px rgba(0,0,0,0.08)',
        minWidth: 170,
      }}>
        <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#94a3b8', marginBottom: 8 }}>
          Platform
        </div>
        {LEGEND.map(({ label, color }) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5 }}>
            <div style={{ width: 10, height: 10, borderRadius: 3, background: color, flexShrink: 0 }} />
            <span style={{ fontSize: 11, color: '#475569' }}>{label}</span>
          </div>
        ))}

        <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#94a3b8', marginTop: 12, marginBottom: 8 }}>
          Interface
        </div>
        {EDGE_LEGEND.map(({ label, style }) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5 }}>
            <div style={{ width: 22, height: 0, ...style, flexShrink: 0 }} />
            <span style={{ fontSize: 11, color: '#475569' }}>{label}</span>
          </div>
        ))}

        <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#94a3b8', marginTop: 12, marginBottom: 6 }}>
          Node status
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 4 }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#22c55e', display: 'inline-block', flexShrink: 0 }} />
          <span style={{ fontSize: 11, color: '#475569' }}>ECS service · running</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#f59e0b', display: 'inline-block', flexShrink: 0 }} />
          <span style={{ fontSize: 11, color: '#475569' }}>AWS managed resource</span>
        </div>
      </div>
    </div>
  )
}
