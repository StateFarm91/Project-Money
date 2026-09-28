"""No network in certification, including when Windows needs a local asyncio self-pipe.

Windows implements socketpair with a private loopback listener. Blocking socket.connect
also blocks that implementation. This narrow replacement connects only to the listener
it just created; it never accepts a destination from callers. Ordinary loopback traffic,
outbound connections, connect_ex and DNS are all still refused.
"""
import os
import socket


def install():
    originals = (socket.socket.connect, socket.socket.connect_ex,
                 socket.create_connection, socket.getaddrinfo, socket.socketpair)

    def refuse(*args, **kwargs):
        raise OSError('network refused by the certification harness')

    def local_pair(family=None, type=socket.SOCK_STREAM, proto=0):
        if os.name != 'nt':
            if family is None:
                return originals[4](type=type, proto=proto)
            return originals[4](family=family, type=type, proto=proto)
        if family not in (None, socket.AF_INET) or type != socket.SOCK_STREAM or proto != 0:
            raise ValueError('only an internal IPv4 stream socket pair is supported')
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client = server = None
        try:
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            listener.settimeout(5)
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(5)
            originals[0](client, listener.getsockname())
            server, peer = listener.accept()
            if peer != client.getsockname():
                raise OSError('unexpected peer on private socket pair')
            client.settimeout(None)
            server.settimeout(None)
            return server, client
        except BaseException:
            if client is not None:
                client.close()
            if server is not None:
                server.close()
            raise
        finally:
            listener.close()

    socket.socket.connect = refuse
    socket.socket.connect_ex = refuse
    socket.create_connection = refuse
    socket.getaddrinfo = refuse
    socket.socketpair = local_pair

    def restore():
        (socket.socket.connect, socket.socket.connect_ex, socket.create_connection,
         socket.getaddrinfo, socket.socketpair) = originals
    return restore
