// Drives inkstone/search/client/search.js under node for test_client.py:
// one JSON job on stdin, one JSON result on stdout. The DOM below is only as
// real as attach() needs it to be.
"use strict";

const fs = require("fs");
const vm = require("vm");

let refusedPatterns = 0;
if (process.env.INKSTONE_NO_PROPERTY_ESCAPES) {
  // Pretend to be an engine from before ES2018 so the client has to fall
  // back to its hand-made character class.
  const NativeRegExp = RegExp;
  global.RegExp = function (pattern, flags) {
    if (String(pattern).indexOf("\\p{") !== -1) {
      refusedPatterns += 1;
      throw new SyntaxError("Invalid regular expression: invalid property name");
    }
    return new NativeRegExp(pattern, flags);
  };
}

const client = require(process.argv[2]);

class FakeElement {
  constructor(doc, tagName) {
    this.ownerDocument = doc;
    this.tagName = tagName.toUpperCase();
    this.parent = null;
    this.children = [];
    this.attributes = {};
    this.listeners = {};
    this.text = "";
    this.id = "";
    this.className = "";
    this.value = "";
    this.href = "";
    this.hidden = false;
    const classes = new Set();
    this.classList = {
      add: (name) => classes.add(name),
      remove: (name) => classes.delete(name),
      contains: (name) => classes.has(name),
    };
  }

  get firstChild() {
    return this.children[0] || null;
  }

  get textContent() {
    return this.text + this.children.map((child) => child.textContent).join("");
  }

  set textContent(value) {
    this.children = [];
    this.text = value;
  }

  appendChild(child) {
    child.parent = this;
    this.children.push(child);
    return child;
  }

  removeChild(child) {
    this.children.splice(this.children.indexOf(child), 1);
    child.parent = null;
    return child;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  getAttribute(name) {
    return name in this.attributes ? this.attributes[name] : null;
  }

  removeAttribute(name) {
    delete this.attributes[name];
  }

  addEventListener(type, listener) {
    (this.listeners[type] = this.listeners[type] || []).push(listener);
  }

  removeEventListener(type, listener) {
    this.listeners[type] = (this.listeners[type] || []).filter((fn) => fn !== listener);
  }

  dispatch(type, init) {
    const event = Object.assign(
      {
        type: type,
        target: this,
        defaultPrevented: false,
        preventDefault() {
          this.defaultPrevented = true;
        },
      },
      init || {}
    );
    (this.listeners[type] || []).slice().forEach((listener) => listener(event));
    return event;
  }

  contains(node) {
    for (let current = node; current; current = current.parent) {
      if (current === this) return true;
    }
    return false;
  }

  find(tagName) {
    let found = [];
    this.children.forEach((child) => {
      if (child.tagName === tagName) found.push(child);
      found = found.concat(child.find(tagName));
    });
    return found;
  }

  querySelector(selector) {
    return this.find(selector.toUpperCase())[0] || null;
  }

  click() {
    this.ownerDocument.clicked.push(this.href);
  }
}

function fakeDocument() {
  const doc = new FakeElement(null, "#document");
  doc.clicked = [];
  doc.createElement = (tagName) => new FakeElement(doc, tagName);
  doc.createTextNode = (text) => {
    const node = new FakeElement(doc, "#text");
    node.text = text;
    return node;
  };
  return doc;
}

function snapshot(doc, input, results) {
  const items = results.children.filter((child) => child.getAttribute("role") === "option");
  return {
    hidden: results.hidden,
    expanded: input.getAttribute("aria-expanded"),
    items: items.map((item) => item.textContent),
    links: items.map((item) => item.querySelector("a").href),
    marks: results.find("MARK").map((mark) => mark.textContent),
    active: items.findIndex((item) => item.classList.contains("is-active")),
    selected: items.filter((item) => item.getAttribute("aria-selected") === "true").length,
    activedescendant: input.getAttribute("aria-activedescendant"),
    empty: results.children
      .filter((child) => child.className === "inkstone-search-empty")
      .map((child) => child.textContent),
    clicked: doc.clicked.slice(),
  };
}

function settle() {
  return new Promise((resolve) => setTimeout(resolve, 25));
}

async function runUi(job) {
  const doc = fakeDocument();
  const input = doc.createElement("input");
  const results = doc.createElement(job.container || "ul");
  const outside = doc.createElement("div");
  const handle = client.attach(input, results, job.options);
  const snapshots = [snapshot(doc, input, results)];
  const prevented = [];
  for (const step of job.steps) {
    if (step.type === "input") {
      input.value = step.value;
      input.dispatch("input");
    } else if (step.type === "key") {
      prevented.push(input.dispatch("keydown", { key: step.key }).defaultPrevented);
    } else if (step.type === "focus") {
      input.dispatch("focus");
    } else if (step.type === "click-outside") {
      doc.dispatch("click", { target: outside });
    } else if (step.type === "destroy") {
      handle.destroy();
    }
    await settle();
    snapshots.push(snapshot(doc, input, results));
  }
  return {
    snapshots: snapshots,
    prevented: prevented,
    role: input.getAttribute("role"),
    controls: input.getAttribute("aria-controls") === results.id,
    listeners: Object.keys(input.listeners)
      .map((type) => input.listeners[type].length)
      .reduce((sum, count) => sum + count, 0),
  };
}

async function main() {
  const job = JSON.parse(fs.readFileSync(0, "utf8"));
  const out = { refusedPatterns: refusedPatterns };

  out.stems = (job.words || []).map((word) => client.stem(word));
  out.folded = (job.fold || []).map((text) => client.fold(text));
  out.tokens = (job.texts || []).map((text) =>
    client.tokenize(text).map((t) => [t.text, t.position, t.start, t.end, t.joined])
  );

  if (job.index) {
    const index = new client.Index(job.index);
    const fields = job.index.fields;
    out.parsed = (job.queries || []).map((query) =>
      client.parseQuery(query, fields).map((c) => [c.kind, c.text, c.field, c.occur])
    );
    out.results = (job.queries || []).map((query) => index.search(query, { limit: job.limit }));
    out.suggestions = (job.prefixes || []).map((prefix) => index.suggest(prefix, { limit: 5 }));
    out.highlights = (job.highlights || []).map((item) => index.highlight(item[0], item[1]));
    out.defaultLimit = index.search(job.queries[0]).length;
  }

  if (job.asScript) {
    // the way a page gets it: no module system, just a global
    const page = {};
    page.self = page;
    vm.runInNewContext(fs.readFileSync(process.argv[2], "utf8"), page);
    out.globals = Object.keys(page).filter((name) => name !== "self");
    out.api = Object.keys(page.InkstoneSearch).sort();
    out.scriptStem = page.InkstoneSearch.stem("generators");
  }

  if (job.badIndex) {
    try {
      new client.Index(job.badIndex);
      out.badIndexError = null;
    } catch (err) {
      out.badIndexError = err.message;
    }
  }

  if (job.ui) {
    // attach() is given a url, so the index comes through load() and fetch
    const fetched = [];
    global.fetch = (url) => {
      fetched.push(url);
      const found = url === job.ui.options.url;
      return Promise.resolve({
        ok: found,
        status: found ? 200 : 404,
        json: () => Promise.resolve(job.index),
      });
    };
    try {
      client.search("anything");
      out.searchBeforeLoad = null;
    } catch (err) {
      out.searchBeforeLoad = err.message;
    }
    out.missing = await client.load("/nope.json").then(
      () => null,
      (err) => err.message
    );
    out.ui = await runUi(job.ui);
    out.fetched = fetched;
    out.searchAfterLoad = client.search(job.queries[0], { limit: 1 }).map((hit) => hit.id);
    out.suggestAfterLoad = client.suggest(job.prefixes[0]);
    if (job.uiEmpty) out.uiEmpty = await runUi(job.uiEmpty);
  }

  process.stdout.write(JSON.stringify(out));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
