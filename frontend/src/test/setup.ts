import '@testing-library/jest-dom/vitest'

// jsdom doesn't implement `elementFromPoint` — `input-otp` polls it
// internally (to detect a password-manager icon overlapping a slot) and
// throws an uncaught `TypeError` in test environments without this stub.
if (!document.elementFromPoint) {
  document.elementFromPoint = () => null
}
