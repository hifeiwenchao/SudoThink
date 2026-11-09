const ADMIN_SITE_HOST = 'admin.feiwenchao.com'

export function isAdminSite(): boolean {
  return window.location.hostname === ADMIN_SITE_HOST
}
