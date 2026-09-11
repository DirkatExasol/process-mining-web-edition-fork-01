import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// ── ReactFlow (@xyflow/react) needs a few browser APIs jsdom lacks. Nodes are
// NOT auto-measured (the ResizeObserver is a no-op), which is deliberate: it lets
// a render test verify that our nodes stay visible purely from their declared
// `initialWidth`/`measured` — the fields that keep nodes/edges from vanishing on
// the mid-drag rebuild (see reactflow-drag-hidden-nodes).
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}
if (!(globalThis as { DOMMatrixReadOnly?: unknown }).DOMMatrixReadOnly) {
  ;(globalThis as { DOMMatrixReadOnly?: unknown }).DOMMatrixReadOnly = class {
    m22 = 1
    constructor(_t?: string) {}
  }
}

// crypto.randomUUID exists in jsdom under Node 20+, but guard just in case.
if (!globalThis.crypto?.randomUUID) {
  // @ts-expect-error minimal shim for tests
  globalThis.crypto = { randomUUID: () => '00000000-0000-4000-8000-000000000000' }
}

afterEach(() => cleanup())
