export function getLoginRedirect(redirect: unknown): string {
  if (typeof redirect !== 'string' || !redirect.startsWith('/') || redirect.startsWith('//')
    || /[\\\p{Cc}]/u.test(redirect)) return '/admin'
  return redirect
}
