import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listWorkflows, requestRun } from '../api.js'

export default function NewRun() {
  const navigate = useNavigate()
  const [workflows, setWorkflows] = useState(null)
  const [workflowName, setWorkflowName] = useState('')
  const [loadError, setLoadError] = useState(null)

  const [stage, setStage] = useState('')
  const [startFrom, setStartFrom] = useState('')
  const [stopAfter, setStopAfter] = useState('')
  const [inputs, setInputs] = useState([{ key: '', value: '' }])
  const [promote, setPromote] = useState(false)
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    listWorkflows()
      .then((names) => {
        setWorkflows(names)
        setWorkflowName((current) => current || names[0] || '')
      })
      .catch((e) => setLoadError(e.message))
  }, [])

  function updateInput(index, field, value) {
    setInputs((prev) => prev.map((row, i) => (i === index ? { ...row, [field]: value } : row)))
  }

  function addInputRow() {
    setInputs((prev) => [...prev, { key: '', value: '' }])
  }

  function removeInputRow(index) {
    setInputs((prev) => prev.filter((_, i) => i !== index))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setFormError(null)

    if (!workflowName) {
      setFormError('Choose a workflow.')
      return
    }
    if (stage && (startFrom || stopAfter)) {
      setFormError('Stage cannot be combined with start-from/stop-after -- use one or the other.')
      return
    }

    const body = {}
    const resolvedStartFrom = stage || startFrom || null
    const resolvedStopAfter = stage || stopAfter || null
    if (resolvedStartFrom) body.start_from = resolvedStartFrom
    if (resolvedStopAfter) body.stop_after = resolvedStopAfter

    const inputVersions = {}
    for (const { key, value } of inputs) {
      if (key.trim() === '') continue
      const parsed = Number(value)
      if (!Number.isInteger(parsed)) {
        setFormError(`Input "${key}" needs an integer version.`)
        return
      }
      inputVersions[key.trim()] = parsed
    }
    if (Object.keys(inputVersions).length > 0) body.input_versions = inputVersions
    if (promote) body.promote = true

    setSubmitting(true)
    try {
      await requestRun(workflowName, body)
      navigate('/')
    } catch (err) {
      setFormError(err.message)
      setSubmitting(false)
    }
  }

  if (loadError) return <p className="error">{loadError}</p>
  if (workflows === null) return <p className="muted">Loading...</p>

  return (
    <div className="page-narrow">
      <h1>New run</h1>

      <form onSubmit={handleSubmit} className="card form">
        <label>
          Workflow
          <select value={workflowName} onChange={(e) => setWorkflowName(e.target.value)}>
            {workflows.length === 0 && <option value="">No workflows found</option>}
            {workflows.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>

        <label>
          Stage (single-stage run)
          <input value={stage} onChange={(e) => setStage(e.target.value)} placeholder="e.g. score_items" />
        </label>
        <label>
          Start from
          <input value={startFrom} onChange={(e) => setStartFrom(e.target.value)} disabled={!!stage} />
        </label>
        <label>
          Stop after
          <input value={stopAfter} onChange={(e) => setStopAfter(e.target.value)} disabled={!!stage} />
        </label>

        <fieldset>
          <legend>Input versions</legend>
          <p className="hint">Pins for dependencies this run's start stage won't produce itself.</p>
          {inputs.map((row, i) => (
            <div key={i} className="input-row">
              <input
                placeholder="resource name"
                value={row.key}
                onChange={(e) => updateInput(i, 'key', e.target.value)}
              />
              <input
                placeholder="version"
                value={row.value}
                onChange={(e) => updateInput(i, 'value', e.target.value)}
              />
              <button type="button" className="btn-ghost" onClick={() => removeInputRow(i)}>
                Remove
              </button>
            </div>
          ))}
          <button type="button" className="btn-ghost" onClick={addInputRow}>
            + Add input
          </button>
        </fieldset>

        <label className="checkbox">
          <input type="checkbox" checked={promote} onChange={(e) => setPromote(e.target.checked)} />
          Promote produced versions to current
        </label>

        {formError && <p className="error">{formError}</p>}

        <button type="submit" className="btn-primary" disabled={submitting || !workflowName}>
          {submitting ? 'Requesting...' : 'Trigger run'}
        </button>
      </form>
    </div>
  )
}
