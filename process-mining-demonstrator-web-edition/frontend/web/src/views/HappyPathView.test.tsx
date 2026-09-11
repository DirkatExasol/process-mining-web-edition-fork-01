/** Happy Path editor — the series-parallel node model: add steps, add a split
 *  (branches that rejoin), and confirm the recursive editor renders it. */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { act, cleanup, fireEvent, screen } from '@testing-library/react'
import { HappyPathView } from './HappyPathView'
import { renderSettled } from '../test/renderSettled'
import { useStore } from '../store'
import { stepNode } from '../graph/happyPath'
import { readSetting, writeSetting } from '../settings'

beforeEach(() => {
  localStorage.clear()
  writeSetting('happyPath.editorWidth', 460) // reset the in-memory settings cache too
})

afterEach(async () => {
  // HappyPathView's mount/update effect kicks off store.refreshHappyPathConformance()
  // (async). In these synchronous tests it resolves after the test body — flush it inside
  // act() so its trailing setState is wrapped, then unmount. Without this React logs
  // "update … not wrapped in act(...)".
  await act(async () => {
    await new Promise((r) => setTimeout(r))
  })
  cleanup()
})

async function setup(nodes = [stepNode('A'), stepNode('B')]) {
  useStore.setState({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    selectedProject: { projectId: 'p', title: 'Proj' } as any,
    allSteps: ['A', 'B', 'C', 'D', 'E'],
    happyPaths: [{ id: 'HP1', name: 'Ideal', nodes }],
    selectedHappyPathId: 'HP1',
    happyPathScores: {},
    // No transitions → left pane shows a light "no data" state, not the flow chart.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    processGraph: { steps: { A: {}, B: {}, C: {}, D: {}, E: {} }, transitions: [] } as any,
    journeyCount: 100,
    isLoading: false,
    // The view's mount/update effect fires this async action whenever a project + paths
    // are present. These tests exercise the editor, not conformance, so stub it to a
    // no-op — otherwise its trailing setState lands outside act() and React warns.
    refreshHappyPathConformance: async () => {},
  })
  await renderSettled(<HappyPathView />)
  fireEvent.click(screen.getByRole('button', { name: /Edit Path/ })) // enter edit mode
  // Let any mount/update async settle inside act before the test interacts.
  await act(async () => {
    await new Promise((r) => setTimeout(r))
  })
}

describe('HappyPathView editor', () => {
  it('adds a split (rejoinable branches) into the sequence', async () => {
    await setup()
    // Both trunk steps render as editable rows.
    expect(screen.getByText('A')).toBeInTheDocument()
    expect(screen.getByText('B')).toBeInTheDocument()

    // Adding a split seeds two branches — the recursive editor renders them.
    const splitBtns = screen.getAllByRole('button', { name: /Split/ })
    fireEvent.click(splitBtns[splitBtns.length - 1]) // the ⑂ Split control
    expect(screen.getByText('Branch 1')).toBeInTheDocument()
    expect(screen.getByText('Branch 2')).toBeInTheDocument()

    // The store now holds a split node after the two steps.
    const path = useStore.getState().happyPaths[0]
    expect(path.nodes).toHaveLength(3)
    expect(path.nodes[2].branches).toHaveLength(2)
  })

  it('supports nesting: a split can be added inside a branch', async () => {
    // Seed a path that already has a split, then split inside branch 1.
    await setup([
      stepNode('A'),
      { id: 'S1', step: '', label: '', branches: [[stepNode('B')], [stepNode('C')]] },
    ])
    // Each node list (top + both branches) has its own ⑂ Split control; the branch
    // controls render before the top-level one, so [0] is inside the first branch.
    const splitBtns = screen.getAllByRole('button', { name: /^⑂ Split$/ })
    expect(splitBtns.length).toBeGreaterThanOrEqual(3)
    fireEvent.click(splitBtns[0]) // split inside the first branch
    const path = useStore.getState().happyPaths[0]
    const branch0 = path.nodes[1].branches[0]
    expect(branch0.some((n) => n.branches.length > 0)).toBe(true) // a nested split exists
  })

  it('names the rejoin point of a split that has a continuation', async () => {
    await setup([
      stepNode('A'),
      { id: 'S1', step: '', label: '', branches: [[stepNode('B')], [stepNode('C')]] },
      stepNode('D'), // continuation → the split rejoins before D, so it can be named
    ])
    fireEvent.click(screen.getByRole('button', { name: /Rejoin:/ }))
    const input = screen.getByRole('textbox')
    fireEvent.change(input, { target: { value: 'Approved' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(useStore.getState().happyPaths[0].nodes[1].rejoinLabel).toBe('Approved')
  })

  it('hides the rejoin control when a split is terminal (no continuation)', async () => {
    await setup([
      stepNode('A'),
      { id: 'S1', step: '', label: '', branches: [[stepNode('B')], [stepNode('C')]] },
    ])
    expect(screen.queryByRole('button', { name: /Rejoin:/ })).toBeNull()
  })

  // jsdom's PointerEvent doesn't carry clientX; dispatch a MouseEvent under the
  // pointer type name (React's handler reads clientX from the native event). Wrap the
  // raw dispatch in act(): unlike fireEvent, dispatchEvent doesn't, so the handler's
  // setState (drag width) would otherwise update outside act and warn.
  const pointer = (el: Element, type: string, clientX: number) =>
    act(() => {
      el.dispatchEvent(new MouseEvent(type, { bubbles: true, clientX }))
    })

  it('resizes the ideal-path pane by dragging the handle and persists the width', async () => {
    await setup()
    const handle = screen.getByRole('separator', { name: /Resize the ideal-path/i })
    // Drag the handle 100px to the left → the right pane widens 460 → 560.
    pointer(handle, 'pointerdown', 500)
    pointer(handle, 'pointermove', 400)
    pointer(handle, 'pointerup', 400)
    expect(readSetting<number>('happyPath.editorWidth', 460)).toBe(560)
  })

  it('double-clicking the handle resets the pane width', async () => {
    await setup()
    const handle = screen.getByRole('separator', { name: /Resize the ideal-path/i })
    pointer(handle, 'pointerdown', 500)
    pointer(handle, 'pointermove', 300)
    pointer(handle, 'pointerup', 300)
    expect(readSetting<number>('happyPath.editorWidth', 460)).toBe(660)
    fireEvent.doubleClick(handle)
    expect(readSetting<number>('happyPath.editorWidth', 460)).toBe(460)
  })
})
