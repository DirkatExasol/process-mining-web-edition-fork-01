/** Passkey (WebAuthn) browser flows for the app. Talks to the GUI server's
 *  `/auth/passkey/*` endpoints (same origin) and does the base64url ↔ ArrayBuffer
 *  conversion the WebAuthn API needs (no @simplewebauthn dependency). */

export interface PasskeyUser {
  username: string
  isAdmin: boolean
  isPower: boolean
  displayName: string | null
  authSource: string | null
  passkeyAllowed: boolean
  mfaAllowed: boolean
  mfaEnabled: boolean
}

export interface PasskeyInfo {
  id: string
  name: string
  createdAt: string
  transports: string
}

export function passkeysSupported(): boolean {
  return typeof window !== 'undefined' && !!window.PublicKeyCredential && !!navigator.credentials
}

/** WebAuthn binds a passkey to a domain (the Relying-Party ID) and only accepts a
 *  real domain name or `localhost` — it rejects bare IP addresses and single-label
 *  hosts. Returns false when the page's host can't be used, so the UI can explain
 *  up front instead of surfacing the browser's raw "effective domain … is not a
 *  valid domain" error (e.g. when reaching the app by IP from another device). */
export function passkeyDomainValid(): boolean {
  if (typeof window === 'undefined') return false
  const host = window.location.hostname
  if (host === 'localhost') return true
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(host)) return false // IPv4
  if (host.includes(':') || host.startsWith('[')) return false // IPv6
  return host.includes('.') // a registrable domain (has at least one dot)
}

/** True when passkeys can actually be used on this page (browser + host both OK). */
export function passkeysUsable(): boolean {
  return passkeysSupported() && passkeyDomainValid()
}

export const PASSKEY_DOMAIN_HINT =
  'Passkeys need a hostname, not an IP address. Reach the server by its name over ' +
  'HTTPS — e.g. its “.local” name — instead of its IP, then try again.'

export const PASSKEY_ALREADY_HINT =
  'A passkey for this account already exists on this device. If it isn’t shown in ' +
  'the list here, remove it from your device’s passkey settings (iOS: Settings → ' +
  'Passwords) and try again.'

/** Map a WebAuthn failure to a friendlier message where we can recognise it. */
export function passkeyErrorMessage(e: unknown): string {
  if (e instanceof DOMException) {
    // The device already holds a passkey for this account (or one listed in
    // excludeCredentials) — iOS/Safari reports this as InvalidStateError.
    if (e.name === 'InvalidStateError') return PASSKEY_ALREADY_HINT
    if (e.name === 'SecurityError' || !passkeyDomainValid()) return PASSKEY_DOMAIN_HINT
  }
  return e instanceof Error ? e.message : String(e)
}

function b64urlToBuf(s: string): ArrayBuffer {
  const pad = s.length % 4 === 0 ? '' : '='.repeat(4 - (s.length % 4))
  const bin = atob(s.replace(/-/g, '+').replace(/_/g, '/') + pad)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return bytes.buffer
}

function bufToB64url(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf)
  let bin = ''
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i])
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

async function postJson(url: string, body?: unknown): Promise<Response> {
  return fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

async function detail(resp: Response, fallback: string): Promise<string> {
  try {
    return (await resp.json()).detail || fallback
  } catch {
    return fallback
  }
}

// ── Authentication (sign in) ──────────────────────────────────────────────────

export async function authenticateWithPasskey(username: string): Promise<PasskeyUser> {
  if (!passkeysSupported()) throw new Error('Passkeys are not supported in this browser.')
  const beginResp = await postJson('/auth/passkey/auth/begin', { username })
  if (!beginResp.ok) throw new Error(await detail(beginResp, 'Passkey sign-in is not available.'))
  const options = await beginResp.json()
  const publicKey: PublicKeyCredentialRequestOptions = {
    ...options,
    challenge: b64urlToBuf(options.challenge),
    allowCredentials: (options.allowCredentials || []).map(
      (c: { id: string; type: string; transports?: string[] }) => ({
        ...c,
        id: b64urlToBuf(c.id),
      }),
    ),
  }
  const assertion = (await navigator.credentials.get({ publicKey })) as PublicKeyCredential | null
  if (!assertion) throw new Error('Passkey sign-in was cancelled.')
  const finishResp = await postJson('/auth/passkey/auth/finish', {
    credential: serializeAssertion(assertion),
  })
  if (!finishResp.ok) throw new Error(await detail(finishResp, 'Passkey sign-in failed.'))
  return finishResp.json()
}

// ── Registration / management (signed in) ─────────────────────────────────────

export async function enrollPasskey(name: string): Promise<void> {
  if (!passkeysSupported()) throw new Error('Passkeys are not supported in this browser.')
  const beginResp = await postJson('/auth/passkey/register/begin')
  if (!beginResp.ok) throw new Error(await detail(beginResp, 'Could not start passkey setup.'))
  const options = await beginResp.json()
  const publicKey: PublicKeyCredentialCreationOptions = {
    ...options,
    challenge: b64urlToBuf(options.challenge),
    user: { ...options.user, id: b64urlToBuf(options.user.id) },
    excludeCredentials: (options.excludeCredentials || []).map(
      (c: { id: string; type: string; transports?: string[] }) => ({
        ...c,
        id: b64urlToBuf(c.id),
      }),
    ),
  }
  const cred = (await navigator.credentials.create({ publicKey })) as PublicKeyCredential | null
  if (!cred) throw new Error('Passkey setup was cancelled.')
  const finishResp = await postJson('/auth/passkey/register/finish', {
    credential: serializeAttestation(cred),
    name,
    transports: getTransports(cred).join(','),
  })
  if (!finishResp.ok) throw new Error(await detail(finishResp, 'Could not register the passkey.'))
}

export async function listPasskeys(): Promise<{ passkeyAllowed: boolean; credentials: PasskeyInfo[] }> {
  const resp = await fetch('/auth/passkey/credentials', { credentials: 'same-origin' })
  if (!resp.ok) throw new Error(await detail(resp, 'Could not load passkeys.'))
  return resp.json()
}

export async function deletePasskey(id: string): Promise<void> {
  const resp = await fetch('/auth/passkey/credentials/' + encodeURIComponent(id), {
    method: 'DELETE',
    credentials: 'same-origin',
  })
  if (!resp.ok) throw new Error(await detail(resp, 'Could not remove the passkey.'))
}

// ── Serialization ─────────────────────────────────────────────────────────────

function getTransports(cred: PublicKeyCredential): string[] {
  const r = cred.response as AuthenticatorAttestationResponse
  return typeof r.getTransports === 'function' ? r.getTransports() : []
}

function serializeAttestation(cred: PublicKeyCredential) {
  const r = cred.response as AuthenticatorAttestationResponse
  return {
    id: cred.id,
    rawId: bufToB64url(cred.rawId),
    type: cred.type,
    response: {
      clientDataJSON: bufToB64url(r.clientDataJSON),
      attestationObject: bufToB64url(r.attestationObject),
      transports: getTransports(cred),
    },
    clientExtensionResults: cred.getClientExtensionResults(),
    authenticatorAttachment: cred.authenticatorAttachment ?? undefined,
  }
}

function serializeAssertion(cred: PublicKeyCredential) {
  const r = cred.response as AuthenticatorAssertionResponse
  return {
    id: cred.id,
    rawId: bufToB64url(cred.rawId),
    type: cred.type,
    response: {
      clientDataJSON: bufToB64url(r.clientDataJSON),
      authenticatorData: bufToB64url(r.authenticatorData),
      signature: bufToB64url(r.signature),
      userHandle: r.userHandle ? bufToB64url(r.userHandle) : undefined,
    },
    clientExtensionResults: cred.getClientExtensionResults(),
    authenticatorAttachment: cred.authenticatorAttachment ?? undefined,
  }
}
