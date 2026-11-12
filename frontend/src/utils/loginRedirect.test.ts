import assert from 'node:assert/strict'
import { test } from 'node:test'
import { getLoginRedirect } from './loginRedirect'

test('login defaults to the admin dashboard when there is no redirect', () => {
  for (const value of [undefined, null, '', [], ['/admin/donations'], 42]) {
    assert.equal(getLoginRedirect(value), '/admin')
  }
})

test('login preserves an internal destination including its query and fragment', () => {
  for (const value of ['/admin/donations', '/articles/12/edit?source=admin#content', '/admin?tab=stats']) {
    assert.equal(getLoginRedirect(value), value)
  }
})

test('full page login navigation cannot leave the site through a redirect query', () => {
  for (const value of [
    'https://evil.example/admin', '//evil.example', '///evil.example',
    '/\\evil.example', '\\evil.example', 'javascript:alert(1)',
    '/\n/evil.example', '/\t/evil.example', '/admin\u0000', 'admin',
  ]) {
    assert.equal(getLoginRedirect(value), '/admin')
  }
})
