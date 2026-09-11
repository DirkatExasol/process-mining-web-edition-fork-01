import { describe, expect, it } from 'vitest'
import { flowKeyframes } from './MetricEdge'

/** The Individual Journey playback dot: each edge animates only during its
 *  1/total slot of a shared loop, in chronological order. */
describe('flowKeyframes', () => {
  it('first edge moves at the start of the loop', () => {
    const kf = flowKeyframes(0, 5)
    // motion: progress 0→1 over [0, 0.2], then hold at 1
    expect(kf.keyTimes).toBe('0.0000;0.2000;1.0000')
    expect(kf.keyPoints).toBe('0.0000;1.0000;1.0000')
    // visible from the very start until 0.2, then hidden
    expect(kf.opacityValues).toBe('1;0')
    expect(kf.opacityTimes).toBe('0;0.2000')
  })

  it('a middle edge holds, moves in its slot, then holds', () => {
    const kf = flowKeyframes(2, 5) // slot [0.4, 0.6]
    expect(kf.keyTimes).toBe('0.0000;0.4000;0.6000;1.0000')
    expect(kf.keyPoints).toBe('0.0000;0.0000;1.0000;1.0000')
    expect(kf.opacityTimes).toBe('0;0.4000;0.6000')
    expect(kf.opacityValues).toBe('0;1;0')
  })

  it('last edge moves at the end and stays visible to the loop end', () => {
    const kf = flowKeyframes(4, 5) // slot [0.8, 1.0]
    expect(kf.keyTimes).toBe('0.0000;0.8000;1.0000')
    expect(kf.keyPoints).toBe('0.0000;0.0000;1.0000')
    // no trailing 0 — visible through the end of the loop, then wraps
    expect(kf.opacityTimes).toBe('0;0.8000')
    expect(kf.opacityValues).toBe('0;1')
  })

  it('a single-edge journey animates the whole loop', () => {
    const kf = flowKeyframes(0, 1)
    expect(kf.keyTimes).toBe('0.0000;1.0000')
    expect(kf.keyPoints).toBe('0.0000;1.0000')
    expect(kf.opacityValues).toBe('1')
  })
})
