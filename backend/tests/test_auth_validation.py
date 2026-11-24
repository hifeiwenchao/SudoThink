"""Login rejects malformed request bodies as API validation errors."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from sanic import Sanic, Request
from app.api.auth import login
from app.api import auth
from app.core.exceptions import ValidationError, UnauthorizedError

class LoginValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_bodies_are_validation_errors(self):
        for body in ({}, [], [1], 'text', 42, None, {'username': 'admin'}):
            with self.subTest(body=body), self.assertRaises(ValidationError) as raised:
                await login(SimpleNamespace(json=body))
            self.assertEqual(raised.exception.status, 422)

    async def test_malformed_json_is_validation_error(self):
        request = Request(b'/auth/login', {'content-type': 'application/json'}, '1.1', 'POST', None, app=Sanic('auth_invalid_json'))
        request.body = b'{bad json'
        with self.assertRaises(ValidationError) as raised:
            await login(request)
        self.assertEqual(raised.exception.status, 422)

    async def test_invalid_password_bytes_do_not_crash_login(self):
        with patch.object(auth.User, 'get_or_none', new=AsyncMock(return_value=SimpleNamespace(password_hash='unused'))):
            for password in ('invalid\x00password', 'x' * 4097):
                with self.subTest(password_length=len(password)), self.assertRaises(UnauthorizedError):
                    await login(SimpleNamespace(json={'username': 'admin', 'password': password}))
