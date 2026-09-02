import { describe, expect, it } from 'vitest'
import { paginate } from './Pagination.jsx'

describe('paginate', () => {
  it('slices the first page by default', () => {
    const items = Array.from({ length: 25 }, (_, i) => i)
    expect(paginate(items, 1, 10)).toEqual({ items: items.slice(0, 10), page: 1, totalPages: 3 })
  })

  it('slices a middle page', () => {
    const items = Array.from({ length: 25 }, (_, i) => i)
    expect(paginate(items, 2, 10).items).toEqual(items.slice(10, 20))
  })

  it('slices a partial last page', () => {
    const items = Array.from({ length: 25 }, (_, i) => i)
    expect(paginate(items, 3, 10).items).toEqual(items.slice(20, 25))
  })

  it('clamps a page beyond the end down to the last page', () => {
    const items = Array.from({ length: 5 }, (_, i) => i)
    // e.g. the list shrank on refresh (a run finished and left "Ongoing")
    // while the user was sitting on a now out-of-range page.
    const result = paginate(items, 99, 10)
    expect(result.page).toBe(1)
    expect(result.items).toEqual(items)
  })

  it('clamps a page below 1 up to 1', () => {
    expect(paginate([1, 2, 3], 0, 10).page).toBe(1)
  })

  it('always reports at least one total page, even for an empty list', () => {
    expect(paginate([], 1, 10)).toEqual({ items: [], page: 1, totalPages: 1 })
  })
})
