import asyncio
import socket
import unittest
from network_guard import install


class NetworkGuardTests(unittest.TestCase):
    def setUp(self):
        self.restore = install()

    def tearDown(self):
        self.restore()

    def test_external_and_ordinary_loopback_paths_stay_blocked(self):
        for address in [('203.0.113.1', 443), ('127.0.0.1', 1)]:
            with socket.socket() as sock:
                with self.assertRaisesRegex(OSError, 'network refused'):
                    sock.connect(address)
                with self.assertRaisesRegex(OSError, 'network refused'):
                    sock.connect_ex(address)
            with self.assertRaisesRegex(OSError, 'network refused'):
                socket.create_connection(address)
        with self.assertRaisesRegex(OSError, 'network refused'):
            socket.getaddrinfo('example.invalid', 443)

    def test_internal_pair_and_real_event_loop_work(self):
        first, second = socket.socketpair()
        try:
            first.sendall(b'local only')
            self.assertEqual(second.recv(32), b'local only')
        finally:
            first.close()
            second.close()
        async def work():
            await asyncio.sleep(0)
            return 'executed'
        self.assertEqual(asyncio.run(work()), 'executed')


if __name__ == '__main__':
    unittest.main()
