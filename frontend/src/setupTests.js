import { TextDecoder, TextEncoder } from "node:util";

globalThis.TextDecoder ??= TextDecoder;
globalThis.TextEncoder ??= TextEncoder;

class TestIntersectionObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() { return []; }
}

globalThis.IntersectionObserver ??= TestIntersectionObserver;
