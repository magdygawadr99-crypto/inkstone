// Search UI glue.
//
// The search client (js/inkstone-search.js) and the index are both sizeable
// and most visitors never search, so neither is fetched until the box is
// used. This file is the small part that is always loaded: it waits for the
// first sign of interest, pulls the rest in, and hands over to
// InkstoneSearch.attach for the dropdown. On the search page it renders the
// full result list for ?q=... itself.
(function () {
  "use strict";

  const box = document.querySelector("[data-search]");
  const page = document.querySelector("[data-search-page]");
  if (!box && !page) return;

  const source = box || page;
  const scriptUrl = source.getAttribute("data-search-script");
  const indexUrl = source.getAttribute("data-search-index");

  let clientPromise = null;
  let indexPromise = null;

  function loadClient() {
    if (window.InkstoneSearch) return Promise.resolve(window.InkstoneSearch);
    if (clientPromise) return clientPromise;
    clientPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = scriptUrl;
      script.async = true;
      script.onload = () => {
        if (window.InkstoneSearch) {
          resolve(window.InkstoneSearch);
        } else {
          reject(new Error("search client loaded but InkstoneSearch is missing"));
        }
      };
      script.onerror = () => reject(new Error("could not load " + scriptUrl));
      document.head.appendChild(script);
    }).catch((err) => {
      // allow another attempt on the next focus
      clientPromise = null;
      throw err;
    });
    return clientPromise;
  }

  // Resolves to the Index object once both the client and the data are in.
  function loadIndex() {
    if (indexPromise) return indexPromise;
    indexPromise = loadClient()
      .then((client) => client.load(indexUrl))
      .catch((err) => {
        indexPromise = null;
        throw err;
      });
    return indexPromise;
  }

  function isTyping(target) {
    if (!target || !target.tagName) return false;
    const tag = target.tagName.toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select" || target.isContentEditable;
  }

  // Header box

  function setupBox() {
    const input = box.querySelector("input[type=search]");
    const results = box.querySelector(".search-box__results");
    if (!input || !results) return;

    let handle = null;
    let starting = false;

    function start() {
      if (handle || starting) return;
      starting = true;
      box.setAttribute("data-state", "loading");
      loadIndex().then(
        () => {
          starting = false;
          box.removeAttribute("data-state");
          handle = window.InkstoneSearch.attach(input, results, {
            limit: 8,
            emptyText: "Nothing found",
          });
          // whatever was typed while the index was on its way
          if (input.value.trim()) handle.update();
        },
        (err) => {
          starting = false;
          box.setAttribute("data-state", "error");
          if (window.console) console.error(err);
        }
      );
    }

    input.addEventListener("focus", start);
    input.addEventListener("input", start);
    // Hovering is a cheap hint that a search is coming; it buys a few hundred
    // milliseconds of head start on slow connections.
    box.addEventListener("pointerenter", start, { once: true });

    input.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      // First Escape closes the results (the client handles that), the next
      // one clears the box, the one after gives the page its focus back.
      if (!results.hidden) return;
      if (input.value) {
        input.value = "";
      } else {
        input.blur();
      }
    });

    // The form still submits to the search page, which is what Enter does
    // when no result is selected. An empty query should not navigate.
    box.addEventListener("submit", (event) => {
      if (!input.value.trim()) event.preventDefault();
    });
  }

  // "/" focuses the search field, as on most documentation sites.
  function setupShortcut() {
    const target =
      (page && document.getElementById("search-page-input")) ||
      (box && box.querySelector("input[type=search]"));
    if (!target) return;

    document.addEventListener("keydown", (event) => {
      if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return;
      if (isTyping(event.target)) return;
      // The header field is hidden while the mobile menu is closed.
      if (target.offsetParent === null) return;
      event.preventDefault();
      target.focus();
      target.select();
    });
  }

  // Search page

  function setupPage() {
    const list = page;
    const status = document.getElementById("search-status");
    const form = document.querySelector("[data-search-form]");
    const input = document.getElementById("search-page-input");
    let timer = null;
    let lastQuery = null;

    function say(message, isError) {
      if (!status) return;
      status.textContent = message;
      status.classList.toggle("search-status--error", Boolean(isError));
    }

    function clear() {
      while (list.firstChild) list.removeChild(list.firstChild);
    }

    function appendHighlighted(parent, index, text, terms) {
      index.highlight(text, terms).forEach((segment) => {
        if (segment[1]) {
          const mark = document.createElement("mark");
          mark.textContent = segment[0];
          parent.appendChild(mark);
        } else {
          parent.appendChild(document.createTextNode(segment[0]));
        }
      });
    }

    function renderHit(hit, index) {
      const terms = [];
      Object.keys(hit.matches || {}).forEach((field) => {
        hit.matches[field].forEach((term) => terms.push(term));
      });
      const stored = hit.stored || {};
      const url = stored.url || hit.id;

      const item = document.createElement("li");
      item.className = "search-result";

      const title = document.createElement("h2");
      title.className = "search-result__title";
      const link = document.createElement("a");
      link.href = url;
      appendHighlighted(link, index, String(stored.title || url), terms);
      title.appendChild(link);
      item.appendChild(title);

      const address = document.createElement("div");
      address.className = "search-result__url";
      address.textContent = url;
      item.appendChild(address);

      if (stored.summary) {
        const summary = document.createElement("p");
        summary.className = "search-result__summary";
        appendHighlighted(summary, index, String(stored.summary), terms);
        item.appendChild(summary);
      }
      return item;
    }

    function run(query, live) {
      query = query.trim();
      if (query === lastQuery) return;
      lastQuery = query;
      if (!query) {
        clear();
        say("");
        return;
      }
      say("Searching\u2026");
      loadIndex().then(
        (index) => {
          // a newer query went out while this one waited for the index
          if (query !== lastQuery) return;
          // While typing, treat the last word as a prefix so results show up
          // before the word is finished. Not inside an open quote.
          let text = query;
          const quotes = (text.match(/"/g) || []).length;
          if (live && quotes % 2 === 0 && /[A-Za-z0-9\u00c0-\uffff]$/.test(text)) text += "*";
          let hits;
          try {
            hits = index.search(text, { limit: 50 });
          } catch (err) {
            say("That query could not be understood.", true);
            return;
          }
          clear();
          const fragment = document.createDocumentFragment();
          hits.forEach((hit) => fragment.appendChild(renderHit(hit, index)));
          list.appendChild(fragment);
          if (!hits.length) {
            say("Nothing found for \u201c" + query + "\u201d.");
          } else if (hits.length === 1) {
            say("1 result for \u201c" + query + "\u201d");
          } else {
            say(hits.length + " results for \u201c" + query + "\u201d");
          }
        },
        (err) => {
          lastQuery = null;
          say("The search index could not be loaded. Try reloading the page.", true);
          if (window.console) console.error(err);
        }
      );
    }

    function queryFromUrl() {
      try {
        return new URLSearchParams(window.location.search).get("q") || "";
      } catch (err) {
        return "";
      }
    }

    // Keep ?q= in step so the page can be bookmarked and the back button
    // returns to the same results.
    function rememberQuery(query) {
      if (!window.history || !window.history.replaceState) return;
      const url = new URL(window.location.href);
      if (query) {
        url.searchParams.set("q", query);
      } else {
        url.searchParams.delete("q");
      }
      window.history.replaceState(null, "", url.toString());
    }

    if (form && input) {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        if (timer !== null) window.clearTimeout(timer);
        rememberQuery(input.value.trim());
        lastQuery = null;
        run(input.value, false);
      });

      input.addEventListener("input", () => {
        if (timer !== null) window.clearTimeout(timer);
        timer = window.setTimeout(() => {
          timer = null;
          rememberQuery(input.value.trim());
          run(input.value, true);
        }, 180);
      });
    }

    window.addEventListener("popstate", () => {
      const query = queryFromUrl();
      if (input) input.value = query;
      run(query, false);
    });

    const initial = queryFromUrl();
    if (input) {
      input.value = initial;
      if (!initial) input.focus();
    }
    if (initial) {
      run(initial, false);
    } else {
      // someone opened the search page: they are going to search
      loadIndex().catch(() => {});
    }
  }

  if (box) setupBox();
  if (page) setupPage();
  setupShortcut();
})();
