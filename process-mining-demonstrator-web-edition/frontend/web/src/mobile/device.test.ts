/** detectPhone — the phone-vs-desktop gate for WorkBench Mobile. A handset UA AND a small
 *  viewport must agree; iPads/tablets/desktops are never phones. */

import { describe, expect, it } from 'vitest'
import { detectPhone } from './device'

function setUA(ua: string) {
  Object.defineProperty(navigator, 'userAgent', { value: ua, configurable: true })
}
function setSize(w: number, h: number) {
  Object.defineProperty(window, 'innerWidth', { value: w, configurable: true })
  Object.defineProperty(window, 'innerHeight', { value: h, configurable: true })
}

describe('detectPhone', () => {
  it('is true for an iPhone, in portrait and landscape', () => {
    setUA('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605 Mobile/15E148')
    setSize(390, 844)
    expect(detectPhone()).toBe(true)
    setSize(844, 390)
    expect(detectPhone()).toBe(true)
  })

  it('is true for an Android phone (UA carries the Mobile token)', () => {
    setUA('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537 Chrome/120 Mobile Safari/537')
    setSize(412, 915)
    expect(detectPhone()).toBe(true)
  })

  it('is false for an Android tablet (no Mobile token)', () => {
    setUA('Mozilla/5.0 (Linux; Android 14; SM-X200) AppleWebKit/537 Chrome/120 Safari/537')
    setSize(800, 1280)
    expect(detectPhone()).toBe(false)
  })

  it('is false for an iPad (iPadOS reports as Mac, wide viewport)', () => {
    setUA('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605 Version/17 Safari/605')
    setSize(1024, 1366)
    expect(detectPhone()).toBe(false)
  })

  it('is false for a desktop browser', () => {
    setUA('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537 Chrome/120 Safari/537')
    setSize(1440, 900)
    expect(detectPhone()).toBe(false)
  })

  it('is false for a phone UA in a desktop-sized window (short side ≥ 600)', () => {
    setUA('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605 Mobile/15E148')
    setSize(1200, 800)
    expect(detectPhone()).toBe(false)
  })
})
