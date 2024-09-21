// Footnote previews: hovering or focusing a footnote reference shows the
// note in a small popover next to it, so reading does not mean jumping to the
// bottom of the page and back. Clicking the reference still works as a link.
(function () {
  "use strict";

  const SHOW_DELAY = 120;
  const HIDE_DELAY = 250;
  const GAP = 8;
  const REF_SELECTOR = 'a.footnote-ref, sup > a[href^="#fn"]';

  let popover = null;
  let currentRef = null;
  let showTimer = null;
  let hideTimer = null;
  let savedTitle = null;

  function noteFor(ref) {
    const href = ref.getAttribute("href") || "";
    if (href.charAt(0) !== "#") return null;
    let id;
    try {
      id = decodeURIComponent(href.slice(1));
    } catch (err) {
      id = href.slice(1);
    }
    return document.getElementById(id);
  }

  // A copy of the note without the "back to text" arrow and without ids
  // (duplicated ids would break the real backlinks).
  function noteContent(note) {
    const copy = note.cloneNode(true);
    const drop = copy.querySelectorAll('.footnote-backref, a[href^="#fnref"]');
    for (let i = 0; i < drop.length; i++) drop[i].parentNode.removeChild(drop[i]);
    const withId = copy.querySelectorAll("[id]");
    for (let i = 0; i < withId.length; i++) withId[i].removeAttribute("id");
    const fragment = document.createDocumentFragment();
    while (copy.firstChild) fragment.appendChild(copy.firstChild);
    return fragment;
  }

  function ensurePopover() {
    if (popover) return popover;
    popover = document.createElement("div");
    popover.className = "footnote-popover content";
    popover.id = "footnote-popover";
    popover.setAttribute("role", "tooltip");
    popover.hidden = true;
    popover.addEventListener("mouseenter", cancelHide);
    popover.addEventListener("mouseleave", scheduleHide);
    document.body.appendChild(popover);
    return popover;
  }

  // Below the reference when there is room, above it otherwise, and never
  // hanging off either side of the window.
  function place(ref) {
    const box = ref.getBoundingClientRect();
    const width = popover.offsetWidth;
    const height = popover.offsetHeight;
    const viewWidth = document.documentElement.clientWidth;
    const viewHeight = window.innerHeight;

    let left = box.left + box.width / 2 - width / 2;
    left = Math.max(GAP, Math.min(left, viewWidth - width - GAP));

    let top = box.bottom + GAP;
    if (top + height > viewHeight - GAP && box.top - GAP - height > 0) {
      top = box.top - GAP - height;
    }

    popover.style.left = Math.round(left + window.scrollX) + "px";
    popover.style.top = Math.round(top + window.scrollY) + "px";
  }

  function show(ref) {
    const note = noteFor(ref);
    if (!note) return;
    if (currentRef && currentRef !== ref) hide();
    ensurePopover();
    while (popover.firstChild) popover.removeChild(popover.firstChild);
    popover.appendChild(noteContent(note));
    if (!popover.textContent.trim()) return;

    // A title attribute (the footnote_previews plugin adds one for readers
    // without JavaScript) would pop up a second, native tooltip on top.
    if (ref.hasAttribute("title")) {
      savedTitle = ref.getAttribute("title");
      ref.removeAttribute("title");
    }
    currentRef = ref;
    ref.setAttribute("aria-describedby", popover.id);
    popover.hidden = false;
    place(ref);
  }

  function hide() {
    cancelShow();
    cancelHide();
    if (!currentRef) return;
    currentRef.removeAttribute("aria-describedby");
    if (savedTitle !== null) {
      currentRef.setAttribute("title", savedTitle);
      savedTitle = null;
    }
    currentRef = null;
    if (popover) popover.hidden = true;
  }

  function cancelShow() {
    if (showTimer !== null) window.clearTimeout(showTimer);
    showTimer = null;
  }

  function cancelHide() {
    if (hideTimer !== null) window.clearTimeout(hideTimer);
    hideTimer = null;
  }

  function scheduleShow(ref) {
    cancelHide();
    cancelShow();
    if (currentRef === ref) return;
    showTimer = window.setTimeout(() => {
      showTimer = null;
      show(ref);
    }, SHOW_DELAY);
  }

  // The delay leaves time to move the pointer from the number into the
  // popover, e.g. to follow a link inside the note.
  function scheduleHide() {
    cancelShow();
    cancelHide();
    hideTimer = window.setTimeout(() => {
      hideTimer = null;
      hide();
    }, HIDE_DELAY);
  }

  function setup() {
    const refs = document.querySelectorAll(REF_SELECTOR);
    if (!refs.length) return;

    for (let i = 0; i < refs.length; i++) {
      const ref = refs[i];
      // backlinks inside the notes match the second half of the selector
      if (ref.closest(".footnotes") || !noteFor(ref)) continue;
      ref.addEventListener("mouseenter", () => scheduleShow(ref));
      ref.addEventListener("mouseleave", scheduleHide);
      ref.addEventListener("focus", () => {
        cancelHide();
        show(ref);
      });
      ref.addEventListener("blur", scheduleHide);
    }

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && currentRef) hide();
    });

    // A tap elsewhere on a touch screen, where there is no mouseleave.
    document.addEventListener("pointerdown", (event) => {
      if (!currentRef) return;
      if (popover.contains(event.target) || currentRef.contains(event.target)) return;
      hide();
    });

    window.addEventListener("resize", () => {
      if (currentRef) place(currentRef);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setup);
  } else {
    setup();
  }
})();
