---
title: Live reload without a dependency
description: A WebSocket server is a handshake, a frame format and about 300 lines.
tags: [inkstone, python, websockets, dev-server]
categories: [inkstone]
series: Building inkstone
---

`inkstone serve` has rebuilt the site on every save since June. What it did
not do was tell the browser, so my writing loop was: save, alt-tab, F5,
alt-tab. I did that several hundred times before admitting that the F5 was
the part worth automating.

<!-- more -->

## The cheap way I did not take

The browser could poll: fetch `/__changed` once a second and reload when
the answer differs. It works and it is ten lines. It also means a request
per second in the server log while I am trying to read the server log, and
up to a second of lag, which is exactly the kind of small friction this
whole project exists to remove.

A WebSocket is the right tool: the server says "reload" at the moment the
build finishes. The standard library has no WebSocket server. Here we go
again.

## The handshake

A WebSocket starts life as an ordinary HTTP request with a few extra
headers. The server proves it understood by hashing the client's key with a
fixed GUID from the RFC[^guid] and sending the result back.

```python {hl_lines="4"}
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

def accept_key(client_key: str) -> str:
    digest = hashlib.sha1((client_key + GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")

def handshake(request) -> bytes:
    key = request.headers["Sec-WebSocket-Key"]
    return (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept_key(key)}\r\n"
        "\r\n"
    ).encode("ascii")
```

After those bytes, the socket stops being HTTP.

## Frames

Everything after the handshake travels in frames. For live reload the
server only ever *sends* short text frames, which is the easy direction:

```python
def text_frame(message: str) -> bytes:
    payload = message.encode("utf-8")
    header = bytearray([0x81])              # FIN + opcode 1 (text)
    if len(payload) < 126:
        header.append(len(payload))
    elif len(payload) < 65536:
        header.append(126)
        header += struct.pack("!H", len(payload))
    else:
        header.append(127)
        header += struct.pack("!Q", len(payload))
    return bytes(header) + payload
```

Receiving is where the rest of the 300 lines went. Frames from a browser
are masked with a four-byte key, can be split into fragments, and control
frames (ping, pong, close) may arrive between the fragments of a message.

{{< details summary="The frame layout, for the next time I need it" >}}
```text
 0               1               2               3
 0 1 2 3 4 5 6 7 0 1 2 3 4 5 6 7 0 1 2 3 4 5 6 7 0 1 2 3 4 5 6 7
+-+-+-+-+-------+-+-------------+-------------------------------+
|F|R|R|R| opcode|M| Payload len |    Extended payload length    |
|I|S|S|S|  (4)  |A|     (7)     |          (16 or 64 bits)      |
|N|V|V|V|       |S|             |                               |
| |1|2|3|       |K|             |                               |
+-+-+-+-+-------+-+-------------+-------------------------------+
|        Masking key (if MASK set), then the payload ...        |
+---------------------------------------------------------------+
```

Opcodes I handle: `0x0` continuation, `0x1` text, `0x8` close, `0x9` ping,
`0xA` pong. Binary frames (`0x2`) are answered with a close, since nothing
here should be sending them.
{{< /details >}}

## The browser side

The dev server injects one script tag before `</body>` in every HTML page
it serves. The files on disk are not touched; `inkstone build` output never
contains it.

```javascript
(function () {
  let delay = 250;

  function connect() {
    const ws = new WebSocket(`ws://${location.host}/__inkstone__/livereload`);
    ws.onopen = () => { delay = 250; };
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "reload") location.reload();
      if (msg.type === "css") swapStylesheets(msg.paths);
      if (msg.type === "error") showOverlay(msg);
    };
    ws.onclose = () => {
      setTimeout(connect, delay);
      delay = Math.min(delay * 2, 5000);    // back off while the server is down
    };
  }

  connect();
})();
```

Two niceties fell out almost for free once the channel existed:

- **CSS without a reload.** If the only files that changed are stylesheets,
  the server sends their paths and the script re-points the `<link>` tags
  with a cache-busting query string. Scroll position survives.
- **Errors in the browser.** When a build fails, the message, file and line
  go down the socket and the page shows them in an overlay instead of
  silently staying stale. Fix the error, save, and the overlay goes away.

## Threads, briefly

The HTTP server, the file watcher and each open WebSocket are threads. I
know. But there are at most three browser tabs, the shared state is one
list of sockets behind one lock, and it let me use `http.server` instead of
writing an event loop as well. Even I have limits.

[^guid]: RFC 6455, section 1.3. The GUID is the same for every WebSocket
    connection ever made. It is not a secret; it only exists so a server
    cannot be tricked into the handshake by something that is not a
    WebSocket client.
