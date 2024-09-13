// Light/dark switch.
//
// This file is loaded in <head> without defer so the stored choice is applied
// before anything is painted. The button is wired up later, once it exists.
(function () {
  "use strict";

  const STORAGE_KEY = "inkstone-theme";
  const root = document.documentElement;
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

  root.classList.remove("no-js");
  root.classList.add("js");

  // localStorage throws in some private modes and when cookies are blocked.
  function readStored() {
    try {
      const value = window.localStorage.getItem(STORAGE_KEY);
      return value === "light" || value === "dark" ? value : null;
    } catch (err) {
      return null;
    }
  }

  function writeStored(value) {
    try {
      if (value === null) {
        window.localStorage.removeItem(STORAGE_KEY);
      } else {
        window.localStorage.setItem(STORAGE_KEY, value);
      }
    } catch (err) {
      // the choice still holds for this page view
    }
  }

  function systemTheme() {
    return systemDark.matches ? "dark" : "light";
  }

  function currentTheme() {
    return root.getAttribute("data-theme") || systemTheme();
  }

  // null means "follow the system": no attribute, the media query decides.
  function apply(choice) {
    if (choice === null) {
      root.removeAttribute("data-theme");
    } else {
      root.setAttribute("data-theme", choice);
    }
  }

  apply(readStored());

  function updateButton(button) {
    const next = currentTheme() === "dark" ? "light" : "dark";
    const label = "Switch to " + next + " theme";
    button.setAttribute("aria-label", label);
    button.setAttribute("title", label);
    button.setAttribute("aria-pressed", String(currentTheme() === "dark"));
  }

  function updateButtons() {
    const buttons = document.querySelectorAll("[data-theme-toggle]");
    for (let i = 0; i < buttons.length; i++) updateButton(buttons[i]);
  }

  function toggle() {
    const next = currentTheme() === "dark" ? "light" : "dark";
    // Picking what the system already says goes back to following it, so a
    // reader who toggles twice is not stuck with an override forever.
    const choice = next === systemTheme() ? null : next;
    apply(choice);
    writeStored(choice);
    updateButtons();
  }

  function setup() {
    const buttons = document.querySelectorAll("[data-theme-toggle]");
    for (let i = 0; i < buttons.length; i++) {
      buttons[i].hidden = false;
      buttons[i].addEventListener("click", toggle);
    }
    updateButtons();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setup);
  } else {
    setup();
  }

  // The system switched (sunset, say) while the page is open.
  function onSystemChange() {
    if (readStored() === null) apply(null);
    updateButtons();
  }

  if (systemDark.addEventListener) {
    systemDark.addEventListener("change", onSystemChange);
  } else if (systemDark.addListener) {
    // Safari before 14
    systemDark.addListener(onSystemChange);
  }

  // Another tab changed the setting.
  window.addEventListener("storage", function (event) {
    if (event.key !== STORAGE_KEY && event.key !== null) return;
    apply(readStored());
    updateButtons();
  });
})();
