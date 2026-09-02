// Shared layout math for rendering a workflow's stage DAG (list view,
// grouped-by-depth run detail, and the static structure graph) -- one
// source of truth for "how deep is this stage" so all three stay
// consistent with each other and with the Scheduler's own dispatch order
// (stages become dispatchable together exactly when they share a depth).

// Depth = longest path from a root (a stage with no in-graph
// dependency), counting only dependencies that are themselves registered
// stages -- an external dependency (e.g. raw_events, injected directly
// into the Resource Store) never contributes to it.
export function stageDepths(stages) {
  const byName = Object.fromEntries(stages.map((s) => [s.name, s]))
  const depth = {}

  function depthOf(name) {
    if (name in depth) return depth[name]
    depth[name] = 0 // cycle guard; the DAG is acyclic in practice
    const deps = byName[name].depends_on.filter((d) => d in byName)
    depth[name] = deps.length === 0 ? 0 : 1 + Math.max(...deps.map(depthOf))
    return depth[name]
  }

  for (const stage of stages) depthOf(stage.name)
  return depth
}

// Groups stages by depth, in registration order within each level --
// parallel branches (multiple stages at the same depth) land in the same
// row. A plain chain produces one stage per level.
export function depthLevels(stages) {
  const depth = stageDepths(stages)
  const levels = []
  for (const stage of stages) {
    ;(levels[depth[stage.name]] ??= []).push(stage)
  }
  return levels
}

// Full graph layout, including external (stage-less) dependencies as
// their own leftmost column -- e.g. raw_events, injected directly into
// the Resource Store rather than produced by any stage here. Returns
// { levels, edges }: `levels[d]` is the list of nodes at depth `d`
// (`{ name, kind: 'external' | 'stage', retries? }`), `edges` is a list
// of [fromName, toName] pairs.
export function graphLayout(stages) {
  const byName = Object.fromEntries(stages.map((s) => [s.name, s]))
  const depth = stageDepths(stages)

  const externalNames = [
    ...new Set(stages.flatMap((s) => s.depends_on.filter((d) => !(d in byName)))),
  ].sort()

  const shift = externalNames.length > 0 ? 1 : 0 // reserve a column for externals only if any exist

  const levels = []
  for (const name of externalNames) {
    ;(levels[0] ??= []).push({ name, kind: 'external', depends_on: [] })
  }
  for (const stage of stages) {
    const d = depth[stage.name] + shift
    ;(levels[d] ??= []).push({ name: stage.name, kind: 'stage', retries: stage.retries, depends_on: stage.depends_on })
  }
  for (let i = 0; i < levels.length; i++) levels[i] ??= []

  const edges = []
  for (const stage of stages) {
    for (const dep of stage.depends_on) edges.push([dep, stage.name])
  }

  return { levels, edges }
}
