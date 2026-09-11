import { describe, expect, it } from 'vitest'

import { boundsFromCenter, boundsFromRect, computeGuides } from './alignGuides'

describe('boundsFromCenter / boundsFromRect', () => {
  it('derives six edges from a centre', () => {
    expect(boundsFromCenter(100, 50, 40, 20)).toEqual({
      left: 80,
      cx: 100,
      right: 120,
      top: 40,
      cy: 50,
      bottom: 60,
    })
  })

  it('derives six edges from a top-left rect', () => {
    expect(boundsFromRect(10, 20, 100, 40)).toEqual({
      left: 10,
      cx: 60,
      right: 110,
      top: 20,
      cy: 40,
      bottom: 60,
    })
  })
})

describe('computeGuides', () => {
  const moving = boundsFromCenter(100, 100, 40, 20)

  it('returns nothing with no targets', () => {
    const g = computeGuides(moving, [])
    expect(g.vertical).toEqual([])
    expect(g.horizontal).toEqual([])
    expect(g.snapDx).toBe(0)
    expect(g.snapDy).toBe(0)
  })

  it('aligns centre-x to a target within threshold and snaps', () => {
    // target centred 4px to the right — within the default 6px threshold
    const target = boundsFromCenter(104, 300, 40, 20)
    const g = computeGuides(moving, [target])
    expect(g.vertical.some((l) => l.x === 104)).toBe(true)
    expect(g.snapDx).toBe(4) // move the item +4 so centres coincide
    expect(g.snapDy).toBe(0)
  })

  it('ignores targets beyond the threshold', () => {
    const target = boundsFromCenter(200, 100, 40, 20) // every edge >6px away
    const g = computeGuides(moving, [target])
    expect(g.vertical).toEqual([])
    expect(g.snapDx).toBe(0)
  })

  it('aligns left edges and top edges independently', () => {
    // shares a left edge (80) and a top edge (90 vs 90) — moving.top is 90
    const target = boundsFromRect(80, 90, 200, 20)
    const g = computeGuides(moving, [target])
    expect(g.vertical.some((l) => l.x === 80)).toBe(true) // left-to-left
    expect(g.horizontal.some((l) => l.y === 90)).toBe(true) // top-to-top
    expect(g.snapDx).toBe(0)
    expect(g.snapDy).toBe(0)
  })

  it('spans a vertical guide across both boxes', () => {
    const target = boundsFromCenter(100, 400, 40, 20) // same cx, far below
    const g = computeGuides(moving, [target])
    const line = g.vertical.find((l) => l.x === 100)
    expect(line).toBeDefined()
    expect(line!.y1).toBe(90) // moving top
    expect(line!.y2).toBe(410) // target bottom
  })

  it('merges several targets that share an x into one line', () => {
    const a = boundsFromCenter(100, 300, 40, 20)
    const b = boundsFromCenter(100, 500, 40, 20)
    const g = computeGuides(moving, [a, b])
    expect(g.vertical.filter((l) => l.x === 100)).toHaveLength(1)
  })

  it('picks the closest target for the snap offset', () => {
    const near = boundsFromCenter(103, 300, 40, 20) // +3
    const far = boundsFromCenter(95, 300, 40, 20) // -5
    const g = computeGuides(moving, [near, far])
    expect(g.snapDx).toBe(3) // nearer wins
  })
})
