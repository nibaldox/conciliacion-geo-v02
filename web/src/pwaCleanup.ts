export async function purgeLegacyApiCache(reload: () => void = () => window.location.reload()): Promise<boolean> {
  try {
    if (!('caches' in window) || !caches || !await caches.has('api-cache')) return false;
    await caches.delete('api-cache');
    if (sessionStorage.getItem('conciliacion.swMigrated') === '1') return false;
    const registrations = await navigator.serviceWorker.getRegistrations();
    await Promise.all(registrations.map((registration) => registration.unregister()));
    sessionStorage.setItem('conciliacion.swMigrated', '1');
    reload();
    return true;
  } catch {
    return false;
  }
}
