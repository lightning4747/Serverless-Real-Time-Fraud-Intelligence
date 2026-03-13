import React, { useRef, useEffect, useState, useCallback } from 'react'
import { TransactionGraph, GraphNode, GraphEdge } from '../types'
import { ZoomIn, ZoomOut, RotateCcw } from 'lucide-react'

interface TransactionGraphVisualizationProps {
  graph: TransactionGraph
  height?: number
}

interface NodePosition {
  id: string
  x: number
  y: number
  vx: number
  vy: number
}

function layoutNodes(nodes: GraphNode[], width: number, height: number): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>()
  const count = nodes.length
  const cx = width / 2
  const cy = height / 2
  const radius = Math.min(width, height) * 0.35

  nodes.forEach((node, i) => {
    if (count === 1) {
      positions.set(node.id, { x: cx, y: cy })
    } else {
      const angle = (i / count) * 2 * Math.PI - Math.PI / 2
      positions.set(node.id, {
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle),
      })
    }
  })
  return positions
}

function getNodeColor(node: GraphNode): string {
  if (node.type === 'account') {
    const risk = node.risk_score || 0
    if (risk >= 0.8) return '#dc2626'
    if (risk >= 0.6) return '#f59e0b'
    if (risk >= 0.3) return '#eab308'
    return '#22c55e'
  }
  return '#3b82f6'
}

function getEdgeColor(edge: GraphEdge): string {
  const amount = edge.amount || 0
  if (amount >= 50000) return '#dc2626'
  if (amount >= 10000) return '#f59e0b'
  return '#9ca3af'
}

export const TransactionGraphVisualization: React.FC<TransactionGraphVisualizationProps> = ({
  graph,
  height = 420,
}) => {
  const svgRef = useRef<SVGSVGElement>(null)
  const [dimensions, setDimensions] = useState({ width: 700, height })
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 })

  const positions = layoutNodes(graph.nodes, dimensions.width, dimensions.height)

  // Observe container resize
  useEffect(() => {
    const el = svgRef.current?.parentElement
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setDimensions({ width: entry.contentRect.width || 700, height })
      }
    })
    ro.observe(el)
    setDimensions({ width: el.clientWidth || 700, height })
    return () => ro.disconnect()
  }, [height])

  const handleZoomIn = () => setZoom((z) => Math.min(z * 1.4, 4))
  const handleZoomOut = () => setZoom((z) => Math.max(z / 1.4, 0.25))
  const handleReset = () => { setZoom(1); setPan({ x: 0, y: 0 }) }

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.target === svgRef.current) {
      setIsDragging(true)
      setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y })
    }
  }

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return
    setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y })
  }

  const handleMouseUp = () => setIsDragging(false)

  const nodeRadius = (node: GraphNode) => node.type === 'account' ? 22 : 14

  return (
    <div className="relative select-none">
      {/* Controls */}
      <div className="absolute top-3 right-3 z-10 flex flex-col space-y-1">
        <button
          onClick={handleZoomIn}
          className="p-1.5 bg-white border border-gray-300 rounded shadow-sm hover:bg-gray-50 transition-colors"
          title="Zoom In"
        >
          <ZoomIn className="h-4 w-4 text-gray-600" />
        </button>
        <button
          onClick={handleZoomOut}
          className="p-1.5 bg-white border border-gray-300 rounded shadow-sm hover:bg-gray-50 transition-colors"
          title="Zoom Out"
        >
          <ZoomOut className="h-4 w-4 text-gray-600" />
        </button>
        <button
          onClick={handleReset}
          className="p-1.5 bg-white border border-gray-300 rounded shadow-sm hover:bg-gray-50 transition-colors"
          title="Reset View"
        >
          <RotateCcw className="h-4 w-4 text-gray-600" />
        </button>
      </div>

      {/* SVG Canvas */}
      <div className="border border-gray-200 rounded-lg overflow-hidden bg-gray-50" style={{ height }}>
        <svg
          ref={svgRef}
          width="100%"
          height={height}
          cursor={isDragging ? 'grabbing' : 'grab'}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        >
          <defs>
            <marker
              id="arrowhead"
              markerWidth="10"
              markerHeight="7"
              refX="10"
              refY="3.5"
              orient="auto"
            >
              <polygon points="0 0, 10 3.5, 0 7" fill="#9ca3af" />
            </marker>
            <marker id="arrowhead-red" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="#dc2626" />
            </marker>
            <marker id="arrowhead-orange" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="#f59e0b" />
            </marker>
          </defs>

          <g transform={`translate(${pan.x},${pan.y}) scale(${zoom})`}>
            {/* Edges */}
            {graph.edges.map((edge) => {
              const src = positions.get(edge.source)
              const tgt = positions.get(edge.target)
              if (!src || !tgt) return null

              const color = getEdgeColor(edge)
              const markerId = color === '#dc2626' ? 'arrowhead-red' : color === '#f59e0b' ? 'arrowhead-orange' : 'arrowhead'

              // Shorten line to avoid overlapping node circle
              const dx = tgt.x - src.x
              const dy = tgt.y - src.y
              const dist = Math.sqrt(dx * dx + dy * dy)
              const srcNode = graph.nodes.find((n) => n.id === edge.source)
              const tgtNode = graph.nodes.find((n) => n.id === edge.target)
              const r1 = srcNode ? nodeRadius(srcNode) : 14
              const r2 = tgtNode ? nodeRadius(tgtNode) : 14

              const x1 = src.x + (dx / dist) * r1
              const y1 = src.y + (dy / dist) * r1
              const x2 = tgt.x - (dx / dist) * (r2 + 8)
              const y2 = tgt.y - (dy / dist) * (r2 + 8)

              const mx = (x1 + x2) / 2
              const my = (y1 + y2) / 2

              return (
                <g key={edge.id}>
                  <line
                    x1={x1} y1={y1} x2={x2} y2={y2}
                    stroke={color}
                    strokeWidth={edge.amount && edge.amount >= 50000 ? 3 : edge.amount && edge.amount >= 10000 ? 2 : 1.5}
                    markerEnd={`url(#${markerId})`}
                  />
                  {edge.amount && (
                    <g>
                      <rect
                        x={mx - 22} y={my - 8} width={44} height={16}
                        rx={4} fill="white" fillOpacity={0.9}
                      />
                      <text
                        x={mx} y={my + 4}
                        textAnchor="middle"
                        fontSize={9}
                        fill="#374151"
                        fontWeight="500"
                      >
                        ${(edge.amount / 1000).toFixed(0)}K
                      </text>
                    </g>
                  )}
                </g>
              )
            })}

            {/* Nodes */}
            {graph.nodes.map((node) => {
              const pos = positions.get(node.id)
              if (!pos) return null
              const color = getNodeColor(node)
              const r = nodeRadius(node)
              const isSelected = selectedNode?.id === node.id

              return (
                <g
                  key={node.id}
                  transform={`translate(${pos.x},${pos.y})`}
                  cursor="pointer"
                  onClick={() => setSelectedNode(isSelected ? null : node)}
                >
                  {/* Selection ring */}
                  {isSelected && (
                    <circle r={r + 5} fill="none" stroke="#2563eb" strokeWidth={2} strokeDasharray="4 2" />
                  )}
                  {/* Node circle */}
                  <circle r={r} fill={color} opacity={0.9} />
                  <circle r={r} fill="none" stroke="white" strokeWidth={1.5} />

                  {/* Risk % label inside account nodes */}
                  {node.type === 'account' && node.risk_score && (
                    <text
                      textAnchor="middle"
                      dy="0.35em"
                      fontSize={9}
                      fill="white"
                      fontWeight="700"
                    >
                      {Math.round(node.risk_score * 100)}%
                    </text>
                  )}

                  {/* Node label below */}
                  <text
                    y={r + 12}
                    textAnchor="middle"
                    fontSize={10}
                    fill="#374151"
                    fontWeight="500"
                  >
                    {node.label.length > 10 ? node.label.slice(0, 10) + '…' : node.label}
                  </text>
                  <text
                    y={r + 23}
                    textAnchor="middle"
                    fontSize={9}
                    fill="#6b7280"
                  >
                    {node.type === 'account' ? 'Account' : 'Transaction'}
                  </text>
                </g>
              )
            })}
          </g>
        </svg>
      </div>

      {/* Selected Node Panel */}
      {selectedNode && (
        <div className="mt-3 p-3 bg-white border border-gray-200 rounded-lg text-sm">
          <div className="flex justify-between items-start mb-2">
            <span className="font-semibold text-gray-900">{selectedNode.label}</span>
            <button onClick={() => setSelectedNode(null)} className="text-gray-400 hover:text-gray-600 text-xs">✕</button>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs text-gray-600">
            <div><span className="font-medium">ID:</span> <span className="font-mono">{selectedNode.id}</span></div>
            <div><span className="font-medium">Type:</span> <span className="capitalize">{selectedNode.type}</span></div>
            {selectedNode.risk_score !== undefined && (
              <div><span className="font-medium">Risk:</span> <span className="text-danger-600 font-bold">{Math.round(selectedNode.risk_score * 100)}%</span></div>
            )}
          </div>
        </div>
      )}

      {/* Legend */}
      <div className="mt-3 flex flex-wrap gap-3 text-xs text-gray-600">
        <div className="flex items-center space-x-1.5">
          <div className="w-3 h-3 rounded-full bg-red-600" />
          <span>High Risk Account</span>
        </div>
        <div className="flex items-center space-x-1.5">
          <div className="w-3 h-3 rounded-full bg-yellow-500" />
          <span>Medium Risk</span>
        </div>
        <div className="flex items-center space-x-1.5">
          <div className="w-3 h-3 rounded-full bg-green-500" />
          <span>Low Risk</span>
        </div>
        <div className="flex items-center space-x-1.5">
          <div className="w-3 h-3 rounded-full bg-blue-500" />
          <span>Transaction</span>
        </div>
        <div className="flex items-center space-x-1.5 ml-3 text-gray-400">
          <span>Click node to inspect • Drag to pan • Zoom controls top-right</span>
        </div>
      </div>
    </div>
  )
}