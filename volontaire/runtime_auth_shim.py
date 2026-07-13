#!/usr/bin/env python3
"""Shim HTTP/1.1 pour le boot du binaire Rust vc-uyr (JSON compact)."""

from __future__ import annotations

import argparse
import socket
import sys
import threading


BODY = b'{"valid":true,"revoked":false}'
RESPONSE = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: application/json\r\n"
    b"Content-Length: " + str(len(BODY)).encode() + b"\r\n"
    b"Connection: close\r\n"
    b"\r\n"
    + BODY
)


def handle(conn: socket.socket) -> None:
    try:
        conn.recv(65536)
        conn.sendall(RESPONSE)
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18000)
    args = parser.parse_args()
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.host, args.port))
    sock.listen(32)
    print(f"runtime-auth-shim on http://{args.host}:{args.port}", flush=True)
    try:
        while True:
            conn, _ = sock.accept()
            threading.Thread(target=handle, args=(conn,), daemon=True).start()
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
