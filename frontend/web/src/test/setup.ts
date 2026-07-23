import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// crypto.randomUUID exists in jsdom under Node 20+, but guard just in case.
if (!globalThis.crypto?.randomUUID) {
  // @ts-expect-error minimal shim for tests
  globalThis.crypto = { randomUUID: () => '00000000-0000-4000-8000-000000000000' }
}

afterEach(() => cleanup())
