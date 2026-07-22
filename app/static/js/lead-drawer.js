/**
 * lead-drawer.js — Vanilla JS drawer for lead details.
 *
 * Depends on: HTMX (loaded globally as htmx).
 * No Alpine.js required.
 *
 * Behaviour:
 *   - HTMX request starts → shows loading state
 *   - HTMX after-swap → opens drawer, focuses it
 *   - Close button, backdrop click, Escape → close
 *   - Focus is trapped inside drawer when open
 *   - Focus returns to trigger element on close
 *   - Body scroll is locked while drawer is open
 *   - Respects prefers-reduced-motion
 */
(function () {
  "use strict";

  var drawerEl = null;
  var contentEl = null;
  var backdropEl = null;
  var closeBtn = null;
  var triggerEl = null;
  var isOpen = false;
  var initialised = false;

  var MOTION_DURATION = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 180;

  function init() {
    if (initialised) return;
    drawerEl = document.getElementById("lead-drawer");
    if (!drawerEl) return;

    contentEl = document.getElementById("lead-drawer-content");
    backdropEl = drawerEl.querySelector(".lf-drawer-backdrop");
    closeBtn = drawerEl.querySelector(".lf-drawer-close");

    // Close on backdrop click
    if (backdropEl) {
      backdropEl.addEventListener("click", close);
    }
    // Close button
    if (closeBtn) {
      closeBtn.addEventListener("click", close);
    }
    // Escape key
    document.addEventListener("keydown", handleEscape);
    // Capture the opener before HTMX swaps focus into the drawer.
    document.addEventListener("click", handleTriggerClick, true);

    // HTMX events
    document.body.addEventListener("htmx:beforeRequest", handleBeforeRequest);
    document.body.addEventListener("htmx:afterSwap", handleAfterSwap);
    document.body.addEventListener("htmx:responseError", handleResponseError);
    document.body.addEventListener("htmx:sendError", handleResponseError);

    initialised = true;
  }

  function handleTriggerClick(evt) {
    var opener = evt.target.closest ? evt.target.closest("[data-drawer-trigger='true']") : null;
    if (opener) {
      triggerEl = opener;
    }
  }

  function handleBeforeRequest(evt) {
    var target = evt.detail.target;
    if (target && target.id === "lead-drawer-content") {
      var opener = evt.detail.elt;
      if (isDrawerOpener(opener)) {
        triggerEl = opener;
      } else if (isDrawerOpener(document.activeElement)) {
        triggerEl = document.activeElement;
      }
      // Show loading state
      showLoading();
    }
  }

  function isDrawerOpener(el) {
    return Boolean(
      el &&
      el.matches &&
      el.matches("[data-drawer-trigger='true']")
    );
  }

  function handleAfterSwap(evt) {
    if (evt.detail.target && evt.detail.target.id === "lead-drawer-content") {
      open();
    }
  }

  function handleResponseError(evt) {
    var target = evt.detail.target;
    if (target && target.id === "lead-drawer-content") {
      contentEl.innerHTML = '<div class="lf-alert" role="alert">Failed to load lead details.</div>';
      open();
    }
  }

  function showLoading() {
    if (!contentEl) return;
    contentEl.innerHTML = '<div class="lf-loading">Loading lead details...</div>';
    contentEl.style.opacity = "0.6";
  }

  function open() {
    if (isOpen) return;
    isOpen = true;
    if (!drawerEl) return;

    drawerEl.classList.remove("lf-drawer-closed");
    drawerEl.classList.add("lf-drawer-open");
    drawerEl.setAttribute("aria-hidden", "false");
    document.body.classList.add("lf-drawer-active");

    // Animate in
    var aside = drawerEl.querySelector(".lf-drawer");
    if (aside) {
      aside.style.transition = "transform " + MOTION_DURATION + "ms ease";
      aside.style.transform = "translateX(0)";
    }
    if (backdropEl) {
      backdropEl.style.transition = "opacity " + MOTION_DURATION + "ms ease";
      backdropEl.style.opacity = "1";
    }

    // Focus first focusable element
    requestAnimationFrame(function () {
      var first = drawerEl.querySelector("button, a, input, select, textarea, [tabindex]:not([tabindex='-1'])");
      if (first) first.focus();
    });
  }

  function close() {
    if (!isOpen) return;
    isOpen = false;
    if (!drawerEl) return;

    var aside = drawerEl.querySelector(".lf-drawer");
    if (aside) {
      aside.style.transition = "transform " + Math.round(MOTION_DURATION * 0.6) + "ms ease";
      aside.style.transform = "translateX(100%)";
    }
    if (backdropEl) {
      backdropEl.style.transition = "opacity " + Math.round(MOTION_DURATION * 0.6) + "ms ease";
      backdropEl.style.opacity = "0";
    }

    drawerEl.setAttribute("aria-hidden", "true");
    document.body.classList.remove("lf-drawer-active");

    // Restore focus
    if (triggerEl && triggerEl.focus) {
      var opener = triggerEl;
      setTimeout(function () { opener.focus(); }, MOTION_DURATION + 50);
      triggerEl = null;
    }

    // Wait for animation then hide
    setTimeout(function () {
      drawerEl.classList.remove("lf-drawer-open");
      drawerEl.classList.add("lf-drawer-closed");
    }, MOTION_DURATION + 50);
  }

  function handleEscape(evt) {
    if (evt.key === "Escape" && isOpen) {
      close();
    }
  }

  // Auto-init on DOMContentLoaded
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
