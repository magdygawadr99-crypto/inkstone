// Mobile menu: the button in the header opens and closes #site-nav.
//
// The CSS only collapses the menu under 48em and only when the <html> element
// has the "js" class, so if this script fails the links stay visible.
(function () {
  "use strict";

  const toggle = document.querySelector(".nav-toggle");
  if (!toggle) return;
  const nav = document.getElementById(toggle.getAttribute("aria-controls"));
  if (!nav) return;

  const wide = window.matchMedia("(min-width: 48em)");

  toggle.hidden = false;

  function isOpen() {
    return nav.hasAttribute("data-open");
  }

  function open() {
    nav.setAttribute("data-open", "");
    toggle.setAttribute("aria-expanded", "true");
  }

  function close(returnFocus) {
    if (!isOpen()) return;
    nav.removeAttribute("data-open");
    toggle.setAttribute("aria-expanded", "false");
    if (returnFocus) toggle.focus();
  }

  function focusable() {
    return Array.prototype.filter.call(
      nav.querySelectorAll("a[href], button:not([disabled]), input:not([disabled])"),
      (el) => !el.hidden && el.offsetParent !== null
    );
  }

  toggle.addEventListener("click", () => {
    if (isOpen()) {
      close(false);
    } else {
      open();
    }
  });

  // Opening with the keyboard should land on the first link, like a menu
  // button would; a mouse click leaves focus on the button.
  toggle.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowDown") return;
    event.preventDefault();
    open();
    const items = focusable();
    if (items.length) items[0].focus();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !isOpen()) return;
    // The search box uses Escape to close its results first, and says so by
    // preventing the default action.
    if (event.defaultPrevented) return;
    close(nav.contains(document.activeElement));
  });

  // Up/Down move between the links while the menu is open as a column.
  nav.addEventListener("keydown", (event) => {
    if (wide.matches || !isOpen()) return;
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    if (!event.target.classList.contains("site-nav__link")) return;
    const links = Array.prototype.slice.call(nav.querySelectorAll(".site-nav__link"));
    const at = links.indexOf(event.target);
    const next = links[at + (event.key === "ArrowDown" ? 1 : -1)];
    event.preventDefault();
    if (next) {
      next.focus();
    } else if (event.key === "ArrowUp") {
      toggle.focus();
    }
  });

  document.addEventListener("click", (event) => {
    if (!isOpen()) return;
    if (nav.contains(event.target) || toggle.contains(event.target)) return;
    close(false);
  });

  // Tabbing out of the menu closes it, otherwise it hangs open over the page
  // with focus somewhere underneath.
  nav.addEventListener("focusout", (event) => {
    if (wide.matches || !isOpen()) return;
    const to = event.relatedTarget;
    if (to === null || nav.contains(to) || toggle.contains(to)) return;
    close(false);
  });

  // Following a link to an anchor on the same page does not reload, so the
  // menu has to get out of the way by itself.
  nav.addEventListener("click", (event) => {
    const link = event.target.closest ? event.target.closest("a[href]") : null;
    if (link && link.getAttribute("href").charAt(0) === "#") close(false);
  });

  function onResize() {
    if (wide.matches) close(false);
  }

  if (wide.addEventListener) {
    wide.addEventListener("change", onResize);
  } else if (wide.addListener) {
    wide.addListener(onResize);
  }
})();
