// Browser half of inkstone's live reload. The dev server adds a <script> tag
// for this file to every HTML page it serves; none of it ends up in a build.
(function () {
  "use strict";

  // A theme may include the tag by hand as well as the server injecting it.
  if (window.__inkstoneLiveReload) return;
  window.__inkstoneLiveReload = true;

  const SOCKET_PATH = "/__inkstone__/livereload";
  const SCROLL_KEY = "inkstone:scroll";
  const OVERLAY_ID = "inkstone-error-overlay";
  const BUST_PARAM = "_inkstone";
  const MIN_DELAY = 250;
  const MAX_DELAY = 5000;
  const SCROLL_MAX_AGE = 10000;
  const SWAP_TIMEOUT = 3000;

  // Derive the socket address from where this script came from rather than
  // from the page, so it keeps working behind a <base> tag or a proxy.
  const script = document.currentScript;
  const home = new URL(script && script.src ? script.src : location.href);
  const socketUrl =
    (home.protocol === "https:" ? "wss://" : "ws://") + home.host + SOCKET_PATH;

  // The server's standalone error page marks itself. There's no point in
  // drawing an overlay over the same message; there we just wait for good news.
  const onErrorPage = document.documentElement.hasAttribute("data-inkstone-error");

  let socket = null;
  let retryDelay = MIN_DELAY;
  let retryTimer = null;
  let knownBuild = null;
  let leaving = false;
  let reloading = false;

  function log(message) {
    if (window.console && console.debug) console.debug("[inkstone] " + message);
  }

  function connect() {
    retryTimer = null;
    let current;
    try {
      current = new WebSocket(socketUrl);
    } catch (err) {
      // e.g. a content security policy that forbids the connection;
      // retrying won't change its mind
      log("can't open " + socketUrl + ": " + err);
      return;
    }
    socket = current;
    current.addEventListener("open", () => {
      retryDelay = MIN_DELAY;
      log("connected");
    });
    current.addEventListener("message", onMessage);
    current.addEventListener("error", () => current.close());
    current.addEventListener("close", () => {
      if (socket === current) socket = null;
      if (!leaving) scheduleReconnect();
    });
  }

  function scheduleReconnect() {
    if (retryTimer !== null) return;
    // a little jitter so a dozen open tabs don't all knock at once
    const delay = retryDelay * (1 + Math.random() * 0.3);
    retryTimer = setTimeout(connect, delay);
    retryDelay = Math.min(retryDelay * 1.6, MAX_DELAY);
  }

  function reconnectNow() {
    if (socket !== null || leaving) return;
    if (retryTimer !== null) clearTimeout(retryTimer);
    retryDelay = MIN_DELAY;
    connect();
  }

  function onMessage(event) {
    let message;
    try {
      message = JSON.parse(event.data);
    } catch (err) {
      return;
    }
    if (!message || typeof message.type !== "string") return;

    switch (message.type) {
      case "hello":
        // The id changes with every build and every server start. If it
        // moved while we were disconnected, we missed something.
        if (knownBuild !== null && message.build !== knownBuild) fullReload();
        knownBuild = message.build;
        break;
      case "reload":
        fullReload();
        break;
      case "css":
        knownBuild = message.build || knownBuild;
        if (onErrorPage) {
          fullReload();
        } else {
          hideError();
          refreshStylesheets(message.paths || []);
        }
        break;
      case "error":
        showError(message);
        break;
      case "clear":
        if (onErrorPage) {
          fullReload();
        } else {
          hideError();
        }
        break;
      default:
        log("unknown message type: " + message.type);
    }
  }

  function fullReload() {
    if (reloading) return;
    reloading = true;
    saveScroll();
    location.reload();
  }

  function saveScroll() {
    try {
      const state = {
        path: location.pathname,
        x: window.scrollX,
        y: window.scrollY,
        at: Date.now(),
      };
      sessionStorage.setItem(SCROLL_KEY, JSON.stringify(state));
    } catch (err) {
      // storage can be disabled; not worth failing a reload over
    }
  }

  function restoreScroll() {
    let state = null;
    try {
      state = JSON.parse(sessionStorage.getItem(SCROLL_KEY) || "null");
      sessionStorage.removeItem(SCROLL_KEY);
    } catch (err) {
      return;
    }
    if (!state || state.path !== location.pathname) return;
    // Left over from a reload that never came back here (closed tab, error
    // page in between). By now it would just be a surprising jump.
    if (Date.now() - state.at > SCROLL_MAX_AGE) return;

    if ("scrollRestoration" in history) history.scrollRestoration = "manual";
    let touched = false;
    const noteTouch = () => {
      touched = true;
    };
    for (const type of ["wheel", "touchstart", "keydown", "mousedown"]) {
      window.addEventListener(type, noteTouch, { once: true, passive: true });
    }
    const apply = () => {
      if (!touched) window.scrollTo(state.x, state.y);
    };
    apply();
    // Images and fonts still change the page height after this point, so
    // go again once everything is in, unless the reader has moved on.
    if (document.readyState !== "complete") {
      window.addEventListener("load", apply, { once: true });
    }
  }

  function linkPath(link) {
    const pathname = new URL(link.href, location.href).pathname;
    try {
      return decodeURI(pathname);
    } catch (err) {
      return pathname;
    }
  }

  function localStylesheets() {
    const links = document.querySelectorAll('link[rel~="stylesheet"][href]');
    return Array.from(links).filter((link) => {
      if (link.dataset.inkstoneStale) return false;
      try {
        return new URL(link.href, location.href).host === location.host;
      } catch (err) {
        return false;
      }
    });
  }

  function linkMatches(link, path) {
    const wanted = "/" + String(path).replace(/^\/+/, "");
    const actual = linkPath(link);
    return actual === wanted || actual.endsWith(wanted);
  }

  function refreshStylesheets(paths) {
    const links = localStylesheets();
    const matched = links.filter((link) =>
      paths.some((path) => linkMatches(link, path))
    );
    const allFound = paths.every((path) =>
      links.some((link) => linkMatches(link, path))
    );
    // A changed file that no <link> points at was most likely pulled in
    // with @import. There's no telling by whom, so refresh the lot.
    const targets = paths.length > 0 && allFound ? matched : links;
    targets.forEach(swapStylesheet);
    log("refreshed " + targets.length + " stylesheet(s)");
  }

  function swapStylesheet(link) {
    const url = new URL(link.href, location.href);
    url.searchParams.set(BUST_PARAM, Date.now().toString(36));
    const fresh = link.cloneNode(false);
    fresh.href = url.href;

    // Keep the old sheet in place until the new one has loaded, otherwise
    // the page flashes unstyled for a frame or two.
    let settled = false;
    const settle = (loaded) => {
      if (settled) return;
      settled = true;
      if (loaded) {
        link.remove();
      } else {
        // probably caught the file half-written; keep what we had
        fresh.remove();
        delete link.dataset.inkstoneStale;
      }
    };
    fresh.addEventListener("load", () => settle(true));
    fresh.addEventListener("error", () => settle(false));
    // not every browser fires load/error reliably for stylesheets
    setTimeout(() => settle(true), SWAP_TIMEOUT);

    link.dataset.inkstoneStale = "1";
    link.parentNode.insertBefore(fresh, link.nextSibling);
  }

  function showError(message) {
    if (onErrorPage) return;
    hideError();
    const host = document.createElement("div");
    host.id = OVERLAY_ID;
    host.style.cssText = "position:fixed;inset:0;z-index:2147483647;";
    // A shadow root keeps the site's CSS and the overlay's out of each
    // other's way.
    const root = host.attachShadow ? host.attachShadow({ mode: "open" }) : host;
    if (message.html) {
      root.innerHTML = message.html;
    } else {
      const pre = document.createElement("pre");
      pre.textContent =
        (message.title || "Build failed") + "\n\n" + (message.detail || "");
      pre.style.cssText =
        "margin:0;height:100%;overflow:auto;padding:2rem;" +
        "background:#1c1e26;color:#e4e4e7;font:13px/1.5 monospace;";
      root.appendChild(pre);
    }
    root.addEventListener("click", (event) => {
      const target = event.target;
      if (target && target.closest && target.closest("[data-inkstone-dismiss]")) {
        hideError();
      }
    });
    (document.body || document.documentElement).appendChild(host);
  }

  function hideError() {
    const host = document.getElementById(OVERLAY_ID);
    if (host) host.remove();
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideError();
  });

  // Timers are throttled in background tabs, so a tab that lost the server
  // can be far into its backoff. Don't make the user wait when they return.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") reconnectNow();
  });

  window.addEventListener("pagehide", () => {
    leaving = true;
    if (socket !== null) socket.close();
  });

  // pagehide also fires when a page goes into the back/forward cache, and
  // nothing runs this script again when it comes back out of it.
  window.addEventListener("pageshow", (event) => {
    if (!event.persisted) return;
    leaving = false;
    reconnectNow();
  });

  restoreScroll();
  connect();
})();
