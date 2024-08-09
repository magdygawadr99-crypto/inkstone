// Scroll spy for the table of contents: marks the link of the section that
// is currently being read.
//
// An IntersectionObserver watches the headings. Each one is in one of three
// states (above the reading line, on screen, below), and the active entry is
// the first heading on screen or, between headings, the last one scrolled
// past. No scroll listener anywhere.
(function () {
  "use strict";

  const toc = document.querySelector("[data-toc]");
  if (!toc || !("IntersectionObserver" in window)) return;

  const ACTIVE = "is-active";
  // Headings count as "reached" a little below the top edge, and anything in
  // the bottom 60% of the window is not being read yet.
  const ROOT_MARGIN = "-8% 0px -60% 0px";

  // Pair every TOC link with the heading it points to. Links to ids that are
  // not on the page are left alone.
  const entries = [];
  const links = toc.querySelectorAll('a[href^="#"]');
  for (let i = 0; i < links.length; i++) {
    const link = links[i];
    let id;
    try {
      id = decodeURIComponent(link.getAttribute("href").slice(1));
    } catch (err) {
      id = link.getAttribute("href").slice(1);
    }
    const heading = id ? document.getElementById(id) : null;
    if (heading) entries.push({ link: link, heading: heading, state: "below" });
  }
  if (entries.length < 2) return;

  let active = null;

  function setActive(entry) {
    if (entry === active) return;
    if (active) {
      active.link.classList.remove(ACTIVE);
      active.link.removeAttribute("aria-current");
    }
    active = entry;
    if (!active) return;
    active.link.classList.add(ACTIVE);
    active.link.setAttribute("aria-current", "location");
    keepInView(active.link);
  }

  // A long TOC scrolls inside its own box; follow the active entry there
  // without touching the page scroll.
  function keepInView(link) {
    const box = toc.scrollHeight > toc.clientHeight ? toc : null;
    if (!box) return;
    const top = link.offsetTop;
    const bottom = top + link.offsetHeight;
    if (top < box.scrollTop) {
      box.scrollTop = top - 8;
    } else if (bottom > box.scrollTop + box.clientHeight) {
      box.scrollTop = bottom - box.clientHeight + 8;
    }
  }

  function pick() {
    let lastAbove = null;
    for (let i = 0; i < entries.length; i++) {
      if (entries[i].state === "visible") return entries[i];
      if (entries[i].state === "above") lastAbove = entries[i];
    }
    return lastAbove;
  }

  const byHeading = new Map();
  entries.forEach((entry) => byHeading.set(entry.heading, entry));

  const observer = new IntersectionObserver(
    (changes) => {
      changes.forEach((change) => {
        const entry = byHeading.get(change.target);
        if (!entry) return;
        if (change.isIntersecting) {
          entry.state = "visible";
        } else {
          const line = change.rootBounds ? change.rootBounds.top : 0;
          entry.state = change.boundingClientRect.top < line ? "above" : "below";
        }
      });
      setActive(pick());
    },
    { rootMargin: ROOT_MARGIN, threshold: 0 }
  );

  entries.forEach((entry) => observer.observe(entry.heading));

  // Clicking an entry should mark it right away, even when the target is the
  // last heading and the page cannot scroll far enough to make it "active".
  toc.addEventListener("click", (event) => {
    const link = event.target.closest ? event.target.closest('a[href^="#"]') : null;
    if (!link) return;
    for (let i = 0; i < entries.length; i++) {
      if (entries[i].link === link) {
        // let the observer callbacks from the jump land first
        window.setTimeout(() => setActive(entries[i]), 0);
        return;
      }
    }
  });

  // At the very bottom the last sections may never cross the reading line.
  // TODO: this only covers the final entry; two short sections at the end of
  // a post still light up one late.
  const sentinel = document.createElement("div");
  sentinel.setAttribute("aria-hidden", "true");
  sentinel.style.cssText = "height:1px;margin-top:-1px;pointer-events:none";
  document.body.appendChild(sentinel);
  new IntersectionObserver((changes) => {
    if (changes[0].isIntersecting && window.scrollY > 0) {
      setActive(entries[entries.length - 1]);
    } else {
      setActive(pick());
    }
  }).observe(sentinel);
})();
