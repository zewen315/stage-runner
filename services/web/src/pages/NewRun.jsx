import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listStages, listWorkflows, requestRun } from '../api.js'

const BEGINNING = ''

export default function NewRun() {
  const navigate = useNavigate()
  const [workflows, setWorkflows] = useState(null)
  const [workflowName, setWorkflowName] = useState('')
  const [loadError, setLoadError] = useState(null)

  const [stages, setStages] = useState([])
  const [startFrom, setStartFrom] = useState(BEGINNING)
  const [inputs, setInputs] = useState([])
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

  useEffect(() => {
    if (!workflowName) return
    setStartFrom(BEGINNING)
    setInputs([])
    listStages(workflowName)
      .then(setStages)
      .catch((e) => setFormError(e.message))
  }, [workflowName])

  function handleStartFromChange(name) {
    setStartFrom(name)
    if (name === BEGINNING) {
      setInputs([])
      return
    }
    const stage = stages.find((s) => s.name === name)
    setInputs((stage?.depends_on || []).map((dep) => ({ key: dep, value: '' })))
  }

  function updateInputValue(index, value) {
    setInputs((prev) => prev.map((row, i) => (i === index ? { ...row, value } : row)))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setFormError(null)

    if (!workflowName) {
      setFormError('Choose a workflow.')
      return
    }

    const body = {}
    if (startFrom !== BEGINNING) {
      body.start_from = startFrom

      const inputVersions = {}
      for (const { key, value } of inputs) {
        const parsed = Number(value)
        if (value.trim() === '' || !Number.isInteger(parsed)) {
          setFormError(`"${key}" needs an integer version -- ${startFrom} depends on it directly.`)
          return
        }
        inputVersions[key] = parsed
      }
      body.input_versions = inputVersions
    }
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
          Start from
          <select value={startFrom} onChange={(e) => handleStartFromChange(e.target.value)}>
            <option value={BEGINNING}>(Beginning)</option>
            {stages.map((stage) => (
              <option key={stage.name} value={stage.name}>
                {stage.name}
              </option>
            ))}
          </select>
        </label>

        {startFrom !== BEGINNING && (
          <fieldset>
            <legend>Input versions</legend>
            <p className="hint">
              {inputs.length === 0
                ? `${startFrom} has no dependencies of its own.`
                : `${startFrom} depends on these directly -- give each the version to use.`}
            </p>
            {inputs.map((row, i) => (
              <div key={row.key} className="input-row">
                <span className="input-row-label">{row.key}</span>
                <input
                  placeholder="version"
                  value={row.value}
                  onChange={(e) => updateInputValue(i, e.target.value)}
                />
              </div>
            ))}
          </fieldset>
        )}

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
