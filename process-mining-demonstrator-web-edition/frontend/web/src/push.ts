/** Browser Web Push helpers — register the service worker, request permission, subscribe to
 *  push with the backend's VAPID key, and register/unregister the subscription. Per browser /
 *  device; a user enables it once and then any rule with "Web browser push" on can reach them. */

import { api } from './api'

export function pushSupported(): boolean {
  return (
    typeof navigator !== 'undefined' &&
    'serviceWorker' in navigator &&
    typeof window !== 'undefined' &&
    'PushManager' in window &&
    'Notification' in window
  )
}

/** VAPID public key (base64url) → the Uint8Array `applicationServerKey` subscribe() wants. */
function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4)
  const b64 = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(b64)
  const out = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i)
  return out
}

async function existingSubscription(): Promise<PushSubscription | null> {
  if (!pushSupported()) return null
  const reg = await navigator.serviceWorker.getRegistration()
  if (!reg) return null
  return reg.pushManager.getSubscription()
}

/** Whether this browser is currently subscribed to push. */
export async function isPushEnabled(): Promise<boolean> {
  try {
    return (await existingSubscription()) != null
  } catch {
    return false
  }
}

/** Register the SW, ask permission, subscribe, and store the subscription on the backend. */
export async function enablePush(): Promise<void> {
  if (!pushSupported()) {
    throw new Error('Browser notifications are not supported in this browser.')
  }
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') {
    throw new Error('Notification permission was not granted.')
  }
  const reg = await navigator.serviceWorker.register('/sw.js')
  await navigator.serviceWorker.ready
  const { publicKey } = await api.pushKey()
  const sub =
    (await reg.pushManager.getSubscription()) ||
    (await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey) as BufferSource,
    }))
  const json = sub.toJSON() as { endpoint?: string; keys?: { p256dh?: string; auth?: string } }
  await api.pushSubscribe({
    endpoint: json.endpoint || sub.endpoint,
    keys: { p256dh: json.keys?.p256dh || '', auth: json.keys?.auth || '' },
  })
}

/** Unsubscribe this browser and forget it on the backend. */
export async function disablePush(): Promise<void> {
  const sub = await existingSubscription()
  if (!sub) return
  try {
    await api.pushUnsubscribe({ endpoint: sub.endpoint })
  } finally {
    await sub.unsubscribe()
  }
}
