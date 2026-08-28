import "@testing-library/jest-dom/vitest";

// jsdom implements window.scrollTo but not Element.prototype.scrollTo; several
// components call `.scrollTo(...)` on a scrollable ref (e.g. auto-scrolling a
// live match/event log), so stub it out to avoid "not a function" errors.
if (typeof Element !== "undefined" && !Element.prototype.scrollTo) {
  Element.prototype.scrollTo = function scrollTo() {};
}
