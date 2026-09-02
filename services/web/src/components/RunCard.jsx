import { Link } from 'react-router-dom'

// Shared between the Dashboard (mixed workflows, so the pill matters)
// and WorkflowDetail's own recent-runs list (already scoped to one
// workflow, where repeating its name on every card is just noise).
export default function RunCard({ run, showWorkflow = true }) {
  return (
    <Link to={`/workflows/${run.workflow_name}/runs/${run.id}`} className={`run-card status-border-${run.status}`}>
      <div className="run-card-top">
        {showWorkflow && <span className="workflow-pill">{run.workflow_name}</span>}
        <span className={`status status-${run.status}`}>{run.status}</span>
      </div>
      <div className="run-card-meta">
        <span>run #{run.id}</span>
        {run.start_from && <span>from {run.start_from}</span>}
        {run.stop_after && <span>to {run.stop_after}</span>}
      </div>
      <div className="run-card-time">{formatTime(run.requested_at)}</div>
    </Link>
  )
}

function formatTime(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}
