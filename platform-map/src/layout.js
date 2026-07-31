import dagre from '@dagrejs/dagre'

// Approximate rendered dimensions for each node type
const SIZE = {
  serviceNode: { w: 180, h: 78 },
  kongNode:    { w: 215, h: 105 },
}

/**
 * Runs Dagre layout on all non-group nodes and returns a new nodes array.
 * Group containers are hidden during auto-layout — positions are implied
 * by the algorithm. Reset restores the original manual layout.
 *
 * @param {Array}  nodes     - current React Flow nodes
 * @param {Array}  edges     - current React Flow edges
 * @param {string} direction - 'LR' | 'TB' | 'RL' | 'BT'
 */
export function applyDagreLayout(nodes, edges, direction = 'LR') {
  const g = new dagre.graphlib.Graph({ directed: true })
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({
    rankdir:  direction,
    ranksep:  110,   // distance between ranks (columns in LR)
    nodesep:  52,    // distance between nodes in the same rank
    edgesep:  20,
    marginx:  40,
    marginy:  40,
  })

  // Only lay out interactive nodes
  nodes.forEach(node => {
    if (node.type === 'groupNode') return
    const { w, h } = SIZE[node.type] ?? SIZE.serviceNode
    g.setNode(node.id, { width: w, height: h })
  })

  edges.forEach(({ source, target }) => {
    if (g.hasNode(source) && g.hasNode(target)) {
      g.setEdge(source, target)
    }
  })

  dagre.layout(g)

  return nodes.map(node => {
    // Hide group containers — the algo handles visual grouping implicitly
    if (node.type === 'groupNode') return { ...node, hidden: true }

    const n = g.node(node.id)
    if (!n) return node

    return {
      ...node,
      hidden: false,
      position: {
        x: n.x - n.width  / 2,
        y: n.y - n.height / 2,
      },
    }
  })
}
