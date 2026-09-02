import '@testing-library/jest-dom/vitest'

// jsdom doesn't implement `elementFromPoint` — `input-otp` polls it
// internally (to detect a password-manager icon overlapping a slot) and
// throws an uncaught `TypeError` in test environments without this stub.
if (!document.elementFromPoint) {
  document.elementFromPoint = () => null
}

// jsdom doesn't implement `ResizeObserver` — Radix's Tooltip/Popper content
// (e.g. `HelpTooltip`) measures itself with it on mount, throwing an
// uncaught `ReferenceError` in any test that opens one.
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}
