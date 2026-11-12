const ADMIN_SITE_HOST = 'admin.feiwenchao.com'
export const PUBLIC_SITE_URL = 'https://www.feiwenchao.com/'

export function isAdminSite(): boolean {
  return window.location.hostname === ADMIN_SITE_HOST
}
