// Code blocks: a copy button, a language label, and keyboard scrolling for
// blocks that overflow sideways.
(function () {
  "use strict";

  const RESET_AFTER = 1600;
  const GUTTER = ".lineno, .linenos";

  // The text of a block without its line numbers. textContent of the <code>
  // element would include the gutter when the formatter puts it inline.
  function codeText(pre) {
    const source = pre.querySelector("code") || pre;
    const copy = source.cloneNode(true);
    const gutter = copy.querySelectorAll(GUTTER);
    for (let i = 0; i < gutter.length; i++) {
      gutter[i].parentNode.removeChild(gutter[i]);
    }
    return copy.textContent.replace(/\n$/, "");
  }

  function languageOf(pre) {
    const candidates = [pre.querySelector("code"), pre, pre.parentElement];
    for (let i = 0; i < candidates.length; i++) {
      const el = candidates[i];
      if (!el) continue;
      if (el.dataset && el.dataset.lang) return el.dataset.lang;
      const match = /(?:^|\s)lang(?:uage)?-([\w+#.-]+)/.exec(el.className || "");
      if (match) return match[1];
    }
    return "";
  }

  // For browsers (and plain-http dev servers on a LAN address) without the
  // async clipboard API.
  function legacyCopy(text) {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.cssText = "position:fixed;top:0;left:-9999px;opacity:0";
    document.body.appendChild(area);
    area.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (err) {
      ok = false;
    }
    document.body.removeChild(area);
    return ok;
  }

  function copy(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).catch(() => {
        if (!legacyCopy(text)) throw new Error("copy failed");
      });
    }
    return legacyCopy(text) ? Promise.resolve() : Promise.reject(new Error("copy failed"));
  }

  // One polite live region for all blocks, so screen readers hear "Copied"
  // without the button label having to change under the cursor.
  let announcer = null;

  function announce(message) {
    if (!announcer) {
      announcer = document.createElement("div");
      announcer.className = "visually-hidden";
      announcer.setAttribute("role", "status");
      announcer.setAttribute("aria-live", "polite");
      document.body.appendChild(announcer);
    }
    announcer.textContent = "";
    // a fresh text node on the next frame, or repeated messages are dropped
    window.requestAnimationFrame(() => {
      announcer.textContent = message;
    });
  }

  function makeButton(pre) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "code-copy";
    button.textContent = "Copy";
    button.setAttribute("aria-label", "Copy code to clipboard");
    let timer = null;

    function flash(state, label) {
      button.classList.remove("code-copy--done", "code-copy--failed");
      button.classList.add("code-copy--" + state);
      button.textContent = label;
      if (timer !== null) window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        button.classList.remove("code-copy--" + state);
        button.textContent = "Copy";
        timer = null;
      }, RESET_AFTER);
    }

    button.addEventListener("click", () => {
      copy(codeText(pre)).then(
        () => {
          flash("done", "Copied");
          announce("Code copied to clipboard");
        },
        () => {
          flash("failed", "Failed");
          announce("Could not copy the code");
        }
      );
    });
    return button;
  }

  function enhance(pre) {
    // Highlighted blocks already have a wrapper; plain ones get one.
    let box = pre.closest(".highlight");
    if (!box) {
      box = document.createElement("div");
      pre.parentNode.insertBefore(box, pre);
      box.appendChild(pre);
    }
    if (box.classList.contains("code-block")) return;
    box.classList.add("code-block");

    const lang = languageOf(pre);
    if (lang && lang !== "text" && lang !== "plain") {
      const label = document.createElement("span");
      label.className = "code-block__lang";
      label.textContent = lang;
      label.setAttribute("aria-hidden", "true");
      box.appendChild(label);
    }
    box.appendChild(makeButton(pre));
  }

  // A <pre> that scrolls sideways cannot be scrolled with the keyboard unless
  // it can take focus.
  function markScrollable(pre) {
    if (pre.scrollWidth > pre.clientWidth + 1) {
      pre.setAttribute("tabindex", "0");
      pre.setAttribute("role", "region");
      if (!pre.hasAttribute("aria-label")) pre.setAttribute("aria-label", "Code sample");
    } else if (pre.getAttribute("role") === "region") {
      pre.removeAttribute("tabindex");
      pre.removeAttribute("role");
    }
  }

  function setup() {
    const blocks = document.querySelectorAll(".content pre");
    if (!blocks.length) return;
    for (let i = 0; i < blocks.length; i++) {
      // line numbers in a table layout live in their own <pre>
      if (blocks[i].closest("td.linenos")) continue;
      enhance(blocks[i]);
      markScrollable(blocks[i]);
    }

    let pending = null;
    window.addEventListener("resize", () => {
      if (pending !== null) return;
      pending = window.requestAnimationFrame(() => {
        pending = null;
        for (let i = 0; i < blocks.length; i++) markScrollable(blocks[i]);
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setup);
  } else {
    setup();
  }
})();
