"""Small local capture server: tests exercise Python's real SMTP protocol client."""

import socketserver
import ssl
import threading


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        connection = self.request
        stream = None
        try:
            if self.server.mode == "tls":
                connection = self.server.tls_context.wrap_socket(connection, server_side=True)
            stream = connection.makefile("rwb", buffering=0)
            stream.write(b"220 localhost Curbwatch test sink\r\n")
            while True:
                line = stream.readline(1000000)
                if not line:
                    return
                command = line.decode(errors="replace").strip().split(" ", 1)[0].upper()
                self.server.commands.append(command)
                if command in ("EHLO", "HELO"):
                    if self.server.mode == "starttls" and not isinstance(connection, ssl.SSLSocket):
                        stream.write(b"250-localhost\r\n250-STARTTLS\r\n250 AUTH PLAIN\r\n")
                    else:
                        stream.write(b"250-localhost\r\n250 AUTH PLAIN\r\n")
                elif command == "STARTTLS":
                    stream.write(b"220 Ready for TLS\r\n")
                    stream.close()
                    connection = self.server.tls_context.wrap_socket(connection, server_side=True)
                    stream = connection.makefile("rwb", buffering=0)
                elif command in ("MAIL", "RCPT", "RSET", "NOOP"):
                    stream.write(b"250 OK\r\n")
                elif command == "AUTH":
                    stream.write(b"235 Authentication successful\r\n")
                elif command == "DATA":
                    stream.write(b"354 End with a dot\r\n")
                    data = bytearray()
                    while True:
                        chunk = stream.readline(1000000)
                        if chunk == b".\r\n" or not chunk:
                            break
                        data.extend(chunk[1:] if chunk.startswith(b"..") else chunk)
                    if self.server.reject_data:
                        stream.write(f"{self.server.reject_data} Not accepted\r\n".encode())
                    else:
                        self.server.messages.append(bytes(data))
                        if self.server.disconnect_after_data:
                            return
                        stream.write(b"250 Accepted\r\n")
                elif command == "QUIT":
                    stream.write(b"221 Bye\r\n")
                    return
                else:
                    stream.write(b"502 Unsupported test command\r\n")
        except (OSError, ssl.SSLError):
            pass
        finally:
            if stream:
                stream.close()
            connection.close()


class Sink(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, mode="none", tls_context=None):
        self.mode, self.tls_context = mode, tls_context
        self.messages, self.commands = [], []
        self.reject_data = 0
        self.disconnect_after_data = False
        super().__init__(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.shutdown()
        self.server_close()
        self.thread.join(2)
