import { describe, expect, it } from 'vitest'
import { visibleProjects } from './Sidebar'

const P = [
  { projectId: 'BOOKSTORE' },       // normal
  { projectId: 'agg_high1' },       // aggregate high-level map — always visible
  { projectId: 'aggd_detail1' },    // aggregate detail — hidden unless shown/selected
  { projectId: 'aggd_detail2' },
]

describe('visibleProjects (sidebar count == list)', () => {
  it('hides aggregate detail projects when the setting is off', () => {
    const v = visibleProjects(P, false, undefined)
    expect(v.map((p) => p.projectId)).toEqual(['BOOKSTORE', 'agg_high1'])
  })

  it('keeps the currently-open detail project visible even when hidden', () => {
    const v = visibleProjects(P, false, 'aggd_detail2')
    expect(v.map((p) => p.projectId)).toEqual(['BOOKSTORE', 'agg_high1', 'aggd_detail2'])
  })

  it('shows everything when the setting is on', () => {
    expect(visibleProjects(P, true, undefined)).toHaveLength(4)
  })
})
