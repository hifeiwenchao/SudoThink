const ADMIN_SITE_HOST = 'admin.sudothink.test'

export function isAdminSite(): boolean {
  return window.location.hostname === ADMIN_SITE_HOST
}
