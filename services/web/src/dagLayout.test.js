import { describe, expect, it } from 'vitest'
import { depthLevels, graphLayout, stageDepths } from './dagLayout.js'

// Shapes mirror GET /workflows/{name}/stages exactly (see StageInfoResponse
// in workflow_service): { name, depends_on, retries }.

const LINEAR = [
  { name: 'aggregate_signals', depends_on: ['raw_events'], retries: 0 },
  { name: 'score_items', depends_on: ['aggregate_signals'], retries: 0 },
  { name: 'rank_feed', depends_on: ['score_items'], retries: 0 },
  { name: 'publish_feed', depends_on: ['rank_feed'], retries: 0 },
]

// Mirrors workflows/feed_branching: score_items fans out into rank_feed
// and trending_topics, which fan back in at publish_feed.
const BRANCHING = [
  { name: 'aggregate_signals', depends_on: ['raw_events'], retries: 0 },
  { name: 'score_items', depends_on: ['aggregate_signals'], retries: 0 },
  { name: 'rank_feed', depends_on: ['score_items'], retries: 0 },
  { name: 'trending_topics', depends_on: ['score_items'], retries: 0 },
  { name: 'publish_feed', depends_on: ['rank_feed', 'trending_topics'], retries: 0 },
]

describe('stageDepths', () => {
  it('assigns increasing depth down a linear chain', () => {
    expect(stageDepths(LINEAR)).toEqual({
      aggregate_signals: 0,
      score_items: 1,
      rank_feed: 2,
      publish_feed: 3,
    })
  })

  it('gives parallel branches the same depth, and the fan-in one more than either', () => {
    const depth = stageDepths(BRANCHING)
    expect(depth.rank_feed).toBe(depth.trending_topics)
    expect(depth.publish_feed).toBe(depth.rank_feed + 1)
  })

  it('ignores a dependency that is not itself a registered stage', () => {
    // raw_events has no stage of its own -- it must not contribute to
    // aggregate_signals' depth (which should still be 0, a root).
    expect(stageDepths(LINEAR).aggregate_signals).toBe(0)
  })
})

describe('depthLevels', () => {
  it('puts one stage per level for a linear chain', () => {
    const levels = depthLevels(LINEAR)
    expect(levels.map((level) => level.map((s) => s.name))).toEqual([
      ['aggregate_signals'],
      ['score_items'],
      ['rank_feed'],
      ['publish_feed'],
    ])
  })

  it('groups parallel branches into the same level, in registration order', () => {
    const levels = depthLevels(BRANCHING)
    const branchLevel = levels.find((level) => level.length > 1)
    expect(branchLevel.map((s) => s.name)).toEqual(['rank_feed', 'trending_topics'])
  })
})

describe('graphLayout', () => {
  it('places external dependencies in their own leftmost level', () => {
    const { levels } = graphLayout(LINEAR)
    expect(levels[0]).toEqual([{ name: 'raw_events', kind: 'external', depends_on: [] }])
    expect(levels[1][0]).toMatchObject({ name: 'aggregate_signals', kind: 'stage' })
  })

  it('deduplicates an external dependency shared by multiple stages', () => {
    const sharedRoot = [
      { name: 'a', depends_on: ['raw_events'], retries: 0 },
      { name: 'b', depends_on: ['raw_events'], retries: 0 },
    ]
    const { levels } = graphLayout(sharedRoot)
    expect(levels[0]).toHaveLength(1)
  })

  it('produces one edge per dependency, including external ones', () => {
    const { edges } = graphLayout(LINEAR)
    expect(edges).toEqual([
      ['raw_events', 'aggregate_signals'],
      ['aggregate_signals', 'score_items'],
      ['score_items', 'rank_feed'],
      ['rank_feed', 'publish_feed'],
    ])
  })

  it('produces two edges into a fan-in stage', () => {
    const { edges } = graphLayout(BRANCHING)
    const intoPublish = edges.filter(([, to]) => to === 'publish_feed')
    expect(intoPublish).toEqual([
      ['rank_feed', 'publish_feed'],
      ['trending_topics', 'publish_feed'],
    ])
  })

  it('carries retries through onto the stage node', () => {
    const withRetries = [{ name: 'flaky', depends_on: [], retries: 2 }]
    const { levels } = graphLayout(withRetries)
    expect(levels[0][0]).toMatchObject({ name: 'flaky', retries: 2 })
  })
})
