#!/usr/bin/env python3
import argparse
import selectors
import socket
import threading


def parse_addr(raw: str) -> tuple[str, int]:
    host, port = raw.rsplit(":", 1)
    return host, int(port)


def choose_target(client: socket.socket, ssh_addr: tuple[str, int], http_addr: tuple[str, int]) -> tuple[str, int]:
    client.settimeout(2.0)
    try:
        initial = client.recv(64, socket.MSG_PEEK)
    except TimeoutError:
        return ssh_addr
    finally:
        client.settimeout(None)
    return ssh_addr if initial.startswith(b"SSH-") else http_addr


def close_quietly(sock: socket.socket | None) -> None:
    if sock is None:
        return
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


def pump(left: socket.socket, right: socket.socket) -> None:
    selector = selectors.DefaultSelector()
    selector.register(left, selectors.EVENT_READ, right)
    selector.register(right, selectors.EVENT_READ, left)
    try:
        while True:
            events = selector.select()
            if not events:
                continue
            for key, _ in events:
                src = key.fileobj
                dst = key.data
                try:
                    data = src.recv(65536)
                except OSError:
                    return
                if not data:
                    return
                try:
                    dst.sendall(data)
                except OSError:
                    return
    finally:
        selector.close()
        close_quietly(left)
        close_quietly(right)


def handle(client: socket.socket, ssh_addr: tuple[str, int], http_addr: tuple[str, int]) -> None:
    upstream = None
    try:
        upstream = socket.create_connection(choose_target(client, ssh_addr, http_addr), timeout=10)
        upstream.settimeout(None)
        pump(client, upstream)
    except OSError:
        close_quietly(client)
        close_quietly(upstream)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen", default="0.0.0.0:8888")
    parser.add_argument("--ssh", default="127.0.0.1:22")
    parser.add_argument("--http", default="127.0.0.1:8889")
    args = parser.parse_args()

    listen_addr = parse_addr(args.listen)
    ssh_addr = parse_addr(args.ssh)
    http_addr = parse_addr(args.http)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(listen_addr)
        server.listen(256)
        while True:
            client, _ = server.accept()
            threading.Thread(target=handle, args=(client, ssh_addr, http_addr), daemon=True).start()


if __name__ == "__main__":
    main()
