import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach, vi } from 'vitest';

/**
 * Vitest setup, registered in vite.config.js.
 *
 * Every test starts with no stored session and with any stub removed, so a test
 * that signs a user in cannot leak that state into the next one.
 */

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
