import os
import unittest
import uuid
from unittest.mock import patch

from lab import credentials
from lab.devices import validate_device


class CredentialTests(unittest.TestCase):
    def device(self):
        return dict(id=uuid.uuid4().hex, name='Prueba aislada', host='127.0.0.1', port=22, user='test')

    def test_identity_tracks_connection_but_not_display_name(self):
        device = self.device()
        self.assertEqual(credentials.target(device), credentials.target(dict(device, name='Renombrada')))
        for key, value in [('host', '127.0.0.2'), ('port', 23), ('user', 'otro'), ('id', 'otro')]:
            self.assertNotEqual(credentials.target(device), credentials.target(dict(device, **{key: value})))

    def test_one_time_password_takes_priority_and_saved_can_be_disabled(self):
        with patch.object(credentials, 'read_password', return_value='guardada') as reader:
            device = self.device()
            self.assertEqual(credentials.connection_password(device, 'puntual'), 'puntual')
            reader.assert_not_called()
            self.assertIsNone(credentials.connection_password(device, '', False))
            reader.assert_not_called()
            self.assertEqual(credentials.connection_password(device, ''), 'guardada')

    def test_inventory_never_serializes_password(self):
        clean = validate_device(dict(self.device(), password='secreto', remember_password=True))
        self.assertNotIn('password', clean)
        self.assertNotIn('remember_password', clean)

    def test_non_windows_has_no_plaintext_fallback(self):
        with patch.object(credentials, 'supported', return_value=False):
            device = self.device()
            self.assertIsNone(credentials.read_password(device))
            with self.assertRaises(ValueError):
                credentials.save_password(device, 'secreto')

    @unittest.skipUnless(os.name == 'nt', 'Windows Credential Manager')
    def test_windows_round_trip_update_and_delete(self):
        device = self.device()  # No consulta ni altera credenciales de dispositivos reales.
        try:
            self.assertFalse(credentials.has_password(device))
            credentials.save_password(device, 'prueba-sintética-ñ🔐')
            self.assertEqual(credentials.read_password(device), 'prueba-sintética-ñ🔐')
            credentials.save_password(device, 'reemplazo')
            self.assertEqual(credentials.read_password(device), 'reemplazo')
            credentials.forget_password(device)
            credentials.forget_password(device)
            self.assertFalse(credentials.has_password(device))
        finally:
            credentials.forget_password(device)
