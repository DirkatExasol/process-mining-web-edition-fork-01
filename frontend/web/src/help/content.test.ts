import { describe, expect, it } from 'vitest'
import { ADMIN_TOPIC_IDS, HELP_TOPICS } from './content'

describe('help content integrity', () => {
  it('has unique topic ids', () => {
    const ids = HELP_TOPICS.map((t) => t.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('every admin-group id resolves to a real topic (grouping cannot silently break)', () => {
    const ids = new Set(HELP_TOPICS.map((t) => t.id))
    for (const id of ADMIN_TOPIC_IDS) {
      expect(ids, `ADMIN_TOPIC_IDS references missing topic "${id}"`).toContain(id)
    }
  })

  it('groups the expected admin chapters', () => {
    expect(ADMIN_TOPIC_IDS).toEqual([
      'admin-interface',
      'admin-tls',
      'admin-users',
      'admin-connections',
      'admin-directory',
      'admin-logging',
      'backup',
      'admin-customize',
      'admin-license',
    ])
  })

  it('every topic has at least one section with a heading', () => {
    for (const t of HELP_TOPICS) {
      expect(t.sections.length, `topic "${t.id}" has no sections`).toBeGreaterThan(0)
      for (const s of t.sections) expect(s.heading).toBeTruthy()
    }
  })
})
