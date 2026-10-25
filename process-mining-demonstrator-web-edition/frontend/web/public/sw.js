/* Service worker for Process Mining Demonstrator — Web Push notifications.
 * Shows a notification when the backend pushes a triggered-rule alert, and focuses (or opens)
 * the app when the user clicks it. The push payload is JSON: {title, body, tag, ruleId, …}. */

self.addEventListener('push', (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch (_e) {
    data = { title: 'Notification', body: event.data ? event.data.text() : '' }
  }
  const title = data.title || 'Process Mining notification'
  event.waitUntil(
    self.registration.showNotification(title, {
      body: data.body || '',
      tag: data.tag || undefined,
      renotify: !!data.tag,
      data,
      icon: '/logo.svg',
      badge: '/logo.svg',
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ('focus' in client) return client.focus()
      }
      if (self.clients.openWindow) return self.clients.openWindow('/')
      return undefined
    }),
  )
})
