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
