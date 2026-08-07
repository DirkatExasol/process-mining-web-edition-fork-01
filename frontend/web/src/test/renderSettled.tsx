/** Test helpers for components whose mount effects do async work (fetches that resolve
 *  into setState). Rendering such a component with a bare `render()` lets those
 *  resolutions land after React's act() boundary, which logs
 *  "An update to X inside a test was not wrapped in act(...)".
 *
 *  `renderSettled` renders inside act() and lets the mount-effect promise chains resolve
 *  there, so every resulting update is wrapped. `resetStoreOutsideRender` resets shared
 *  store state after unmounting first, so the reset can't re-render (or re-mount a child
 *  into) a still-mounted component and leak an unwrapped update through the back door.
 */
import { act, cleanup, render, type RenderResult } from '@testing-library/react'
import type { ReactElement } from 'react'

export async function renderSettled(ui: ReactElement): Promise<RenderResult> {
  let result: RenderResult
  await act(async () => {
    result = render(ui)
    // A macrotask tick lets chained mount-effect promises (and any child mounted after a
    // post-fetch state change) resolve while act() is still active.
    await new Promise((r) => setTimeout(r))
  })
  return result!
}

/** Run a shared-store reset (e.g. in afterEach) after unmounting everything, so the reset
 *  touches no mounted component. Use instead of a bare `useStore.setState(...)` teardown. */
export function resetStoreOutsideRender(reset: () => void): void {
  cleanup()
  reset()
}
