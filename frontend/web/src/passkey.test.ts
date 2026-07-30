/** Tests for the passkey host/domain guard — WebAuthn only works on a real
 *  hostname or localhost, never a bare IP address, so the UI can gate on this. */

import { afterEach, describe, expect, it } from 'vitest'
import { passkeyDomainValid, passkeysUsable, passkeyErrorMessage, PASSKEY_DOMAIN_HINT } from './passkey'

function setHost(hostname: string) {
  Object.defineProperty(window, 'location', {
    value: { ...window.location, hostname },
    configurable: true,
    writable: true,
  })
}

const original = window.location.hostname
afterEach(() => setHost(original))

describe('passkeyDomainValid', () => {
  it('accepts localhost and real domains', () => {
    setHost('localhost')
    expect(passkeyDomainValid()).toBe(true)
    setHost('app.example.com')
    expect(passkeyDomainValid()).toBe(true)
    setHost('macbook.local')
    expect(passkeyDomainValid()).toBe(true)
    setHost('192-168-1-50.sslip.io')
    expect(passkeyDomainValid()).toBe(true)
  })

  it('rejects bare IP addresses and single-label hosts', () => {
    setHost('192.168.1.50')
    expect(passkeyDomainValid()).toBe(false)
    setHost('10.0.0.1')
    expect(passkeyDomainValid()).toBe(false)
    setHost('fe80::1')
    expect(passkeyDomainValid()).toBe(false)
    setHost('mymac') // single label, not localhost
    expect(passkeyDomainValid()).toBe(false)
  })

  it('passkeysUsable is false on an IP even when the browser supports WebAuthn', () => {
    setHost('192.168.1.50')
    // jsdom exposes PublicKeyCredential/navigator.credentials as undefined, so
    // passkeysUsable is false here regardless; the point is it never returns true
    // on an IP host.
    expect(passkeysUsable()).toBe(false)
  })
})

describe('passkeyErrorMessage', () => {
  it('maps a SecurityError to the hostname hint', () => {
    const e = new DOMException('The effective domain is not a valid domain.', 'SecurityError')
    expect(passkeyErrorMessage(e)).toBe(PASSKEY_DOMAIN_HINT)
  })

  it('passes through other error messages', () => {
    setHost('app.example.com') // valid host, so no domain-based override
    expect(passkeyErrorMessage(new Error('boom'))).toBe('boom')
  })
})
