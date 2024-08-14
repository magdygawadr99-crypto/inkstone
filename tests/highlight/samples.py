from __future__ import annotations

# Snippets of the kind that end up in fenced code blocks, several per
# language. The round-trip tests run every one of them through its lexer;
# the per-language tests pick out individual tokens.

PYTHON = [
    r'''#!/usr/bin/env python3
"""Count words in the files given on the command line."""
from __future__ import annotations

import os.path as osp, sys
from collections import Counter
from . import sibling
from ..pkg.mod import (
    first,
    second as other,
)

MAX_WORDS = 0x_FF + 0b1010 + 0o17 + 1_000


@dataclass(frozen=True)
class Report(Base):
    """What we found."""

    path: str
    ratio: float = 3.14e-10 + 2j + .5

    def __init__(self, path: str) -> None:
        self.path = path

    async def summary(self, *args, **kwargs) -> str:
        if not self.path:
            raise ValueError("bad %s value: {0!r}" % self.path) from None
        yield from args
        return f"{self.path!r:>10}: {kwargs['n']} {{literal}} {self.ratio=:{width}.2f}"


def main(argv: list[str] | None = None) -> int:
    pattern = r"\d+\.\d*" + b"\x00\n".decode() + rb'\raw'.hex() + "a\tb\N{BULLET}"
    counts = Counter()
    for name in argv or sys.argv[1:]:
        with open(name, encoding="utf-8") as fh:
            counts.update(fh.read().split())
    match counts.most_common(1):
        case [(word, n)] if n > 1:
            print(f"{word}: {n}")
        case _:
            print(len(counts), not True, None, lambda q: q ** 2)
    match = 3
    return 0 if counts else ...


if __name__ == "__main__":
    sys.exit(main())
''',
    r"""type Pair = tuple[int, int]

text = '''multi
line %d''' % 3 + 'it''s' + t"hello {name}"
x @= y; z //= 2; w = x if y else z
unterminated = "oops
after = 1
""",
    "def f(x):\r\n    return x  # windows line endings\r\n",
]

JAVASCRIPT = [
    r"""#!/usr/bin/env node
import { readFile } from "node:fs/promises";
export * as utils from "./utils.js";

/** Add two numbers. */
const add = (a, b) => a + b;
const re = /ab+c[/\]]\d/gi, n = 0xFF + 1_000n + .5e3 + 0b11 / 2;
let s = `total: ${items.map((i) => { return { v: i.price * 2 } }).length} \${esc} $x`;

export default class Shape extends Base {
  static #count = 0;
  constructor(name) {
    super(name);
    this.name = name ?? 'unknown\n\u{1F600}';
  }
  get area() {
    return this.w * this.h / 2;
  }
  async *items(limit) {
    for (const x of this.list) yield await x?.load();
  }
}

function* gen() {}
promise.then(r => r.json()).catch(console.error).finally(() => {});
if (typeof x === "undefined" || x instanceof Error) throw new TypeError(`bad`);
obj.default = a ? b : c; i++ / 2; x = y / z / w;
""",
    r"""// event delegation
document.querySelector("#list").addEventListener("click", function (event) {
  const item = event.target.closest("li[data-id]");
  if (!item) return;
  fetch(`/api/items/${item.dataset.id}`, { method: "DELETE" })
    .then((res) => (res.ok ? item.remove() : Promise.reject(res.status)))
    .catch((err) => console.warn("delete failed:", err));
});
/* unterminated string next */
var s = 'abc
var t = null;
""",
]

TYPESCRIPT = [
    r"""import type { Config } from './config';

@Component({ selector: "app" })
export abstract class Store<T extends object> implements Disposable {
  private readonly items = new Map<string, T>();
  constructor(private name: string, public size = 0) {}
  protected async load<K extends keyof T>(key: K): Promise<T[K] | undefined> {
    return (await fetch(`/x/${String(key)}`)).json() as unknown as T[K];
  }
}

interface Props<T> extends Base { readonly id: string; cb?: (v: T) => void }
type Pair = [string, number] | null;
enum Color { Red, Green }
namespace App.Models { export const type = "a"; }
function f(object: Foo, kind = type.kind): asserts object is string {}
declare module "foo" { }
let v = <const>["a"]; let w = x!.y satisfies Z;
""",
]

HTML = [
    r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset=utf-8>
  <title>Tom &amp; Jerry &#169; &bogus</title>
  <!-- a
       comment -->
  <style media="screen">
    body > .card:not(.hidden)::before { margin: 0 auto !important; color: #ff8800 }
    @media (min-width: 600px) { .card { display: grid } }
  </style>
</head>
<body class="home" data-x='1' hidden>
  <p style="color: red; margin: 0 2px" onclick="alert('hi' + 1)">a < b && c</p>
  <br/>
  <script type="module">
    const tpl = `<b>${x}</b>`; if (a < b) { el.innerHTML = "</p>"; }
  </script >
</body>
</html>
""",
    "<ul>\n  <li><a href=page.html>One</a>\n  <li>Two</ul>\n<script>unterminated(",
]

XML = [
    r"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE note [
  <!ENTITY writer "Someone">
]>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Feed &amp; things &#x263A;</title>
    <atom:link href="https://example.com/feed.xml" rel="self"/>
    <!-- items -->
    <item><description><![CDATA[<p>Hello & goodbye</p>]]></description></item>
    <empty attr = 'single' />
  </channel>
</rss>
""",
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
    '<path d="M0 0L10 10" stroke="#000"/></svg>',
]

CSS = [
    r"""@charset "utf-8";
@import url("base.css") screen;
:root { --gap: 1.5rem; --accent: #ff8800; }

/* cards */
body > .card:not(.hidden, #main)::before, a[href^="http" i]:nth-child(2n+1) {
  margin: 0 auto !important;
  background: url(img/bg.png) no-repeat, rgba(0, 0, 0, .5);
  width: calc(100% - var(--gap) * 2); content: "{;}";
  font: italic 12px/1.5 "Helvetica Neue", sans-serif;
  &:hover { color: red }
}
@media (min-width: 600px) and (orientation: landscape) {
  .card { display: grid; transition: all 0.3s ease-in-out }
}
@keyframes spin { from { transform: rotate(0deg) } 50% { opacity: .5 } to { transform: rotate(1turn) } }
@font-face { font-family: "Inter"; src: url(inter.woff2) format("woff2"); unicode-range: U+0000-00FF; }
""",
    "h1,h2{margin:0}\n.a{color:RED;width:-1.5E3PX}\n$broken { x: y\n",
]

JSON = [
    r"""{
  "name": "ink\u00e9 \"stone\"\n",
  "version": 1.5e3, "n": -12, "ok": true, "none": null,
  "list": [1, 2.5, {"nested key": []}],
  "empty": {}
}
""",
    r"""// tsconfig.json
{
  /* compiler */
  "compilerOptions": { "strict": true, "target": "es2022" },
  "bad": "unterminated
}
""",
]

TOML = [
    r"""# comment
title = "TOML \u00e9 \"x\""
[owner.info]
name = 'Tom'   # trailing
dob = 1979-05-27T07:32:00-08:00
"quoted key".sub = 1_000
pi = 3.14e-2
neg = -inf
flag = true
hex = 0xDEAD_BEEF
ports = [ 8001, 8002,
  [1.5, "a"], # nested
]
point = { x = 1.5, y = 2, "k" = [1], t = 07:32:00 }
multi = '''
no \escapes here'''
[[products]]
sku = 738594937
""",
    'text = """\nline \\\n  cont "quoted" """\nbad = "unterminated\nnext = 1\n',
]

YAML = [
    r"""%YAML 1.2
---
# site config
title: "My \"Blog\"\n"   # trailing
base_url: http://example.com/a#frag
'quoted key': 'it''s'
count: 42
ratio: 3.10
version: 1.2.3
hex: 0xFF
enabled: yes
nothing: ~
date: 2024-03-01 10:30:00 +02:00
empty:
defaults: &defaults
  adapter: postgres
  ports: [80, 443, "8080", {a: 1, b: [x, y z]}]
dev:
  <<: *defaults
  tag: !!str 123
description: |
  Line one: with colon
    indented # not a comment

  last
folded: >-
  some text
after: true
...
""",
    r"""name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - name: Run tests
        run: |
          python -m pytest -q
      - - nested
        - -5
      - plain item with: colon
""",
]

INI = [
    r"""; comment
# another
[section one]
key = value with spaces ; trailing comment
color = #fff
path: /usr/bin;/bin
debug = True
port=8080
ratio = 1.5
url = %(base)s/path/${other:name}
skip-networking
install_requires =
    requests>=2.0
    click
[core]
	editor = vim
	pager = less -R
empty =
""",
]

BASH = [
    r"""#!/usr/bin/env bash
set -euo pipefail

readonly ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
count=0; names=(alpha beta "gamma delta")

usage() {
  cat <<EOF | sed 's/^/  /'
Usage: ${0##*/} [-v] <dir>
EOF
  exit 1
}

function build_one {
  local src=$1 out="${2:-build}/$(basename "$src" .md).html"
  [[ -f $src && ! -d "$out" ]] || return 1
  inkstone render "$src" > "$out" 2>&1
}

for f in "$ROOT"/posts/*.md; do
  if build_one "$f"; then
    count=$((count + 1))
  elif [ $? -eq 2 ]; then
    echo "skipped: $f" >&2
  fi
done
case "$1" in
  -v|--verbose) set -x ;;
  *) echo 'no $expansion here' "but \"here\" $count and `date +%s`" ;;
esac
git checkout test && sudo echo done  # trailing comment
""",
    "x=1\ncat <<'END'\n$not_expanded\nEND\necho \"unterminated\n",
]

C = [
    r"""#include <stdio.h>
#include "util.h"
#define MAX(a, b) ((a) > (b) ? (a) : (b)) /* macro */ \
    + 0
#ifdef DEBUG
#endif

/** Entry point. */
typedef struct point { double x, y; } point_t;

static int parse(const char *s, size_t n);

int main(int argc, char **argv) {
    unsigned long mask = 0xFFu | 0755 | 0b101;
    float f = 1.5e-3f + .5 + 10.;
    char c = '\n', *msg = "hi\t%s: %-5.2f%%\n";
    if (argc < 2) goto fail;
    for (int i = 0; i < argc; ++i)
        printf(msg, argv[i], f * i);
    return sizeof(point_t) > 8 ? EXIT_SUCCESS : 1;
fail:
    return -1; // done
}
""",
]

CPP = [
    r"""#include <iostream>
#include <vector>

namespace app::util {

template <typename T>
class Stack final : public Base<T> {
public:
    explicit Stack(std::size_t n) : items_(n) {}
    [[nodiscard]] bool empty() const noexcept { return items_.empty(); }
    void push(T&& value) { items_.push_back(std::move(value)); }
private:
    std::vector<T> items_;
};

enum class Color : unsigned char { Red, Green };

}  // namespace app::util

int main() {
    auto s = std::make_unique<app::util::Stack<int>>(1'000);
    const char* raw = R"sql(SELECT "x" FROM t)sql";
    for (const auto& [k, v] : map) std::cout << k << u8"\u00e9" << '\n';
    return s->empty() ? 0 : nullptr == raw;
}
""",
]

GO = [
    r"""// Package main is a tiny server.
package main

import (
	"fmt"
	"net/http"
)

//go:generate stringer -type=Level
type Level int

const (
	Debug Level = iota
	Info
)

type Server struct {
	Addr string `json:"addr,omitempty"`
	hits map[string]int
}

func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	s.hits[r.URL.Path]++
	fmt.Fprintf(w, "hello %q, visit %d\n", r.URL.Path, s.hits[r.URL.Path])
}

func main() {
	srv := &Server{Addr: ":8080", hits: make(map[string]int)}
	ch := make(chan error, 1)
	go func() { ch <- http.ListenAndServe(srv.Addr, srv) }()
	var mask uint32 = 0xFF &^ 0b1010 | 0o17
	x, r := 1.5e3+2i, 'a'
	if err := <-ch; err != nil {
		panic(err)
	}
	_ = len(srv.hits) + int(mask) + int(real(x)) + int(r)
}
""",
]

RUST = [
    r"""//! Crate docs.
#![allow(dead_code)]
use std::collections::HashMap;

/// A named counter.
#[derive(Debug, Clone, PartialEq)]
pub struct Counter<'a> {
    name: &'a str,
    hits: HashMap<String, u64>,
}

impl<'a> Counter<'a> {
    pub fn new(name: &'a str) -> Self {
        Self { name, hits: HashMap::new() }
    }

    fn bump(&mut self, key: &str) -> Option<u64> {
        let n = self.hits.entry(key.to_string()).or_insert(0);
        *n += 1_u64;
        Some(*n)
    }
}

/* block /* nested */ comment */
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut c = Counter::new("main");
    let raw = r#"a "quoted" \ string"#;
    let pair = (0xff_u8, 1.5e3_f64, b'\n', '\u{1F600}', 2.);
    println!("{}: {:?} {raw} {{literal}} {0:>8.3}\n", c.name, c.bump("x")?);
    'outer: for i in 0..=10 {
        match pair.0 as usize + i {
            MAX => break 'outer,
            n if n % 2 == 0 => continue,
            _ => vec![1, 2, 3].iter().for_each(|v| print!("{v}")),
        }
    }
    Ok(())
}
""",
]

JAVA = [
    r'''package com.example.app;

import java.util.*;
import static java.lang.Math.max;

/**
 * A greeter.
 */
@SuppressWarnings("unchecked")
public final class Greeter<T extends Comparable<T>> implements Runnable {
    private static final int MAX_NAMES = 0x10;
    private final List<String> names = new ArrayList<>();

    public Greeter(String... initial) {
        names.addAll(Arrays.asList(initial));
    }

    @Override
    public void run() {
        long total = 1_000L + 0b101 + 017;
        double avg = 1.5e3 / names.size() + 2f;
        char sep = '\t';
        for (var name : names) {
            System.out.printf("Hello, %s!%n", name == null ? "world" : name);
        }
        String block = """
            multi "line"
            text""";
        Runnable r = () -> System.out.println(block + sep + max(total, (long) avg));
    }

    record Point(int x, int y) {}
    enum Kind { A, B }
}
''',
]

SQL = [
    r"""-- monthly totals
CREATE TABLE IF NOT EXISTS orders (
    id BIGSERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers (id),
    total NUMERIC(10, 2) DEFAULT 0.00,
    note TEXT,
    created_at TIMESTAMP DEFAULT now()
);

/* totals /* nested */ per month */
SELECT c.name, date_trunc('month', o.created_at) AS month,
       COUNT(*) AS n, SUM(o.total)::numeric AS "grand total"
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.note <> 'it''s cancelled' AND o.total >= $1 AND c.region = :region
GROUP BY 1, 2
HAVING count(*) > 1e2
ORDER BY month DESC NULLS LAST
LIMIT 10;

INSERT INTO `log` (msg) VALUES (?), (E'tab\there');
CREATE FUNCTION f() RETURNS int AS $body$ SELECT 1; $body$ LANGUAGE sql;
""",
]

DIFF = [
    r"""diff --git a/inkstone/build.py b/inkstone/build.py
index 3f1a2b4..9c8d7e6 100644
--- a/inkstone/build.py
+++ b/inkstone/build.py
@@ -10,7 +10,8 @@ def build(site):
     pages = collect(site)
-    for page in pages:
-        render(page)
+    for page in sorted(pages):
+        render(page, site)
+    -- not a header
     return len(pages)
\ No newline at end of file
""",
    r"""3c3
< old line
---
> new line
Only in a: stale.txt
*** a.txt	2024-01-01
--- b.txt	2024-01-02
***************
*** 1,2 ****
! changed
""",
]

MARKDOWN = [
    r"""---
title: "Hello"
tags: [a, b]
---

# Heading one

Some *emphasis*, **strong text**, `inline code`, ~~gone~~ and snake_case_name.
A [link](https://example.com "Title"), an ![image](pic.png), a [ref][1] and
<https://auto.link>. Also https://bare.example.org/x, a footnote[^n] &amp; <br/>.

Setext heading
--------------

> quoted *text*
> > nested

- [x] done
- [ ] todo
1. first
2) second

```python {hl_lines="2"}
def f():
    return 1
```

~~~
plain fence
~~~

| a | b |
|---|:-:|
| 1 | 2 |

* * *

[1]: https://example.com/ref "Reference"
[^n]: The note.
""",
    "+++\ntitle = 'x'\n+++\n\nText with \\*escaped\\* stars.\n\n```js\nlet x = 1;\n",
]

DOCKERFILE = [
    r"""# syntax=docker/dockerfile:1
# build stage
FROM --platform=$BUILDPLATFORM python:3.12-slim AS builder
ARG VERSION
ARG TARGET=release
ENV PYTHONUNBUFFERED=1 PATH="/app/bin:${PATH}"
WORKDIR /app
COPY --chown=app:app pyproject.toml cmd/ ./
RUN --mount=type=cache,target=/root/.cache pip install --no-cache-dir . && \
    # trim the image
    rm -rf /var/lib/apt/lists/*

FROM scratch
LABEL org.opencontainers.image.title="inkstone" version=1.0
COPY --from=builder /app /app
EXPOSE 8000/tcp 9000
USER 1000:1000
HEALTHCHECK --interval=30s CMD curl -f http://localhost:8000/ || exit 1
ENTRYPOINT ["inkstone", "serve"]
CMD echo "started $VERSION"
ONBUILD RUN echo hi
""",
]

MAKEFILE = [
    "# build things\n"
    "CC ?= gcc\n"
    "CFLAGS := -Wall -O2 $(EXTRA)\n"
    "SRC = $(wildcard src/*.c)\n"
    "OBJ = $(patsubst src/%.c,build/%.o,$(SRC))\n"
    "\n"
    ".PHONY: all clean\n"
    "all: build/app | build\n"
    "\n"
    "build/%.o: src/%.c include/app.h\n"
    "\t@mkdir -p $(@D)\n"
    "\t$(CC) $(CFLAGS) -c $< -o $@  # compile\n"
    "\n"
    "build/app: $(OBJ) ; $(CC) -o $@ $^\n"
    "\n"
    "ifeq ($(OS),Windows_NT)\n"
    "include win.mk\n"
    "endif\n"
    "\n"
    "clean:\n"
    "\t-rm -rf build && \\\n"
    '\t  for f in *.tmp; do echo "removing $$f"; done\n',
]

TEXT = [
    'Just some text.\nNothing <to> see & nothing to "escape".\n',
    "",
]

SAMPLES: dict[str, list[str]] = {
    "python": PYTHON,
    "javascript": JAVASCRIPT,
    "typescript": TYPESCRIPT,
    "html": HTML,
    "xml": XML,
    "css": CSS,
    "json": JSON,
    "toml": TOML,
    "yaml": YAML,
    "ini": INI,
    "bash": BASH,
    "c": C,
    "cpp": CPP,
    "go": GO,
    "rust": RUST,
    "java": JAVA,
    "sql": SQL,
    "diff": DIFF,
    "markdown": MARKDOWN,
    "dockerfile": DOCKERFILE,
    "makefile": MAKEFILE,
    "text": TEXT,
}
