import { graphLayout } from '../dagLayout.js'

const COL_W = 200
const ROW_H = 64
const NODE_W = 168
const NODE_H = 40
const PAD = 24

export default function WorkflowGraph({ stages }) {
  const { levels, edges } = graphLayout(stages)
  const maxLevelSize = Math.max(1, ...levels.map((level) => level.length))
  const totalHeight = maxLevelSize * ROW_H

  const pos = {}
  levels.forEach((level, d) => {
    const levelHeight = level.length * ROW_H
    const yOffset = (totalHeight - levelHeight) / 2
    level.forEach((node, i) => {
      pos[node.name] = { x: PAD + d * COL_W, y: PAD + yOffset + i * ROW_H }
    })
  })

  const width = PAD * 2 + (levels.length - 1) * COL_W + NODE_W
  const height = PAD * 2 + totalHeight

  return (
    <div className="workflow-graph-scroll">
      <svg width={width} height={height} className="workflow-graph">
        {edges.map(([from, to]) => {
          const a = pos[from]
          const b = pos[to]
          if (!a || !b) return null
          const x1 = a.x + NODE_W
          const y1 = a.y + NODE_H / 2
          const x2 = b.x
          const y2 = b.y + NODE_H / 2
          const midX = (x1 + x2) / 2
          return (
            <path
              key={`${from}->${to}`}
              d={`M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`}
              className="graph-edge"
              markerEnd="url(#graph-arrow)"
            />
          )
        })}

        <defs>
          <marker
            id="graph-arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" className="graph-arrowhead" />
          </marker>
        </defs>

        {levels.flat().map((node) => {
          const { x, y } = pos[node.name]
          return (
            <g key={node.name} transform={`translate(${x}, ${y})`}>
              <rect
                width={NODE_W}
                height={NODE_H}
                rx={8}
                className={node.kind === 'external' ? 'graph-node graph-node-external' : 'graph-node'}
              />
              <text x={NODE_W / 2} y={NODE_H / 2 - (node.retries ? 6 : 0)} className="graph-node-label">
                {node.name}
              </text>
              {node.kind === 'stage' && node.retries > 0 && (
                <text x={NODE_W / 2} y={NODE_H / 2 + 12} className="graph-node-sublabel">
                  retries: {node.retries}
                </text>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}
