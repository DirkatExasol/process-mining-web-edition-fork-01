/** Two-factor (TOTP) self-management for the app. Talks to the GUI server's
 *  `/auth/mfa/*` endpoints (same origin). The login-time code step goes through
 *  the store (`verifyMfa`); this module covers enrolment and recovery codes. */

export interface MfaStatus {
  mfaAllowed: boolean
  enabled: boolean
  recoveryRemaining: number
}

export interface MfaSetup {
  secret: string
  otpauthUri: string
  qrSvg: string
}

async function detail(resp: Response, fallback: string): Promise<string> {
  try {
    return (await resp.json()).detail || fallback
  } catch {
    return fallback
  }
}

async function req<T>(url: string, method: 'GET' | 'POST', body?: unknown): Promise<T> {
  const resp = await fetch(url, {
    method,
    credentials: 'same-origin',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!resp.ok) throw new Error(await detail(resp, 'Request failed.'))
  return resp.json()
}

export function mfaStatus(): Promise<MfaStatus> {
  return req<MfaStatus>('/auth/mfa/status', 'GET')
}

export function mfaSetupBegin(): Promise<MfaSetup> {
  return req<MfaSetup>('/auth/mfa/setup/begin', 'POST')
}

export async function mfaSetupFinish(code: string): Promise<string[]> {
  const r = await req<{ recoveryCodes: string[] }>('/auth/mfa/setup/finish', 'POST', { code })
  return r.recoveryCodes
}

export async function mfaRegenerateRecovery(): Promise<string[]> {
  const r = await req<{ recoveryCodes: string[] }>('/auth/mfa/recovery/regenerate', 'POST')
  return r.recoveryCodes
}

export async function mfaDisable(code: string): Promise<void> {
  // Turning off the second factor requires the current code (server-enforced).
  await req<{ ok: boolean }>('/auth/mfa/disable', 'POST', { code })
}
