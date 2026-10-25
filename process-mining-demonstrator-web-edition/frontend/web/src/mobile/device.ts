/** Phone vs desktop classification for the WorkBench Mobile fork.
 *
 *  A device is a "phone" only when BOTH a handset user-agent AND a small viewport agree.
 *  iPads and Android tablets keep the desktop web layout (iPadOS Safari even reports itself as
 *  a Mac, so it falls through to desktop automatically); the short-side check guards against a
 *  phone UA shown in a desktop-sized window (or a spoofed UA).
 */
import { useEffect } from 'react'
import { useStore } from '../store'

export function detectPhone(): boolean {
  if (typeof navigator === 'undefined' || typeof window === 'undefined') return false
  const ua = navigator.userAgent || ''
  const phoneUA =
    /iPhone|iPod/.test(ua) ||
    (/Android/.test(ua) && /Mobile/.test(ua)) ||
    /Windows Phone|BlackBerry|BB10/.test(ua)
  if (!phoneUA) return false
  // Short side of the viewport — ~<600px covers phones in both orientations; an iPad mini's
  // short side (~768) stays above it, so tablets are never classified as phones.
  const shortSide = Math.min(window.innerWidth, window.innerHeight)
  return shortSide < 600
}

/** Keep `store.isPhone` in sync with the device/viewport, reactively. Returns the value. */
export function useDeviceClass(): boolean {
  useEffect(() => {
    const apply = () => {
      const v = detectPhone()
      if (useStore.getState().isPhone !== v) useStore.setState({ isPhone: v })
    }
    apply()
    window.addEventListener('resize', apply)
    window.addEventListener('orientationchange', apply)
    return () => {
      window.removeEventListener('resize', apply)
      window.removeEventListener('orientationchange', apply)
    }
  }, [])
  return useStore((s) => s.isPhone)
}
