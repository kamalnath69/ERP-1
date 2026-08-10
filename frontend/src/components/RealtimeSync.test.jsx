import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { Provider } from "react-redux";
import RealtimeSync, { REALTIME_FALLBACK_MS } from "./RealtimeSync";

class FakeEventSource {
  static instance;

  constructor() {
    this.listeners = {};
    this.close = vi.fn();
    FakeEventSource.instance = this;
  }

  addEventListener(type, handler) {
    this.listeners[type] = this.listeners[type] || new Set();
    this.listeners[type].add(handler);
  }

  removeEventListener(type, handler) {
    this.listeners[type]?.delete(handler);
  }

  emit(type, data = {}) {
    this.listeners[type]?.forEach((handler) => handler(data));
  }
}

const makeStore = () => ({
  dispatch: vi.fn(),
  getState: () => ({}),
  subscribe: () => () => {},
});

describe("RealtimeSync", () => {
  let container;
  let root;

  beforeEach(() => {
    vi.useFakeTimers();
    global.EventSource = FakeEventSource;
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.useRealTimers();
    delete global.EventSource;
    delete global.IS_REACT_ACT_ENVIRONMENT;
  });

  const renderSync = (store) => {
    act(() => root.render(<Provider store={store}><RealtimeSync /></Provider>));
  };

  test("does not periodically invalidate data while SSE is connected", () => {
    const store = makeStore();
    renderSync(store);

    act(() => FakeEventSource.instance.emit("open"));
    act(() => vi.advanceTimersByTime(REALTIME_FALLBACK_MS * 2));

    expect(store.dispatch).not.toHaveBeenCalled();
  });

  test("uses polling only while SSE is disconnected", () => {
    const store = makeStore();
    renderSync(store);
    act(() => FakeEventSource.instance.emit("open"));
    act(() => FakeEventSource.instance.emit("error"));
    act(() => vi.advanceTimersByTime(REALTIME_FALLBACK_MS));

    expect(store.dispatch).toHaveBeenCalledTimes(1);

    act(() => FakeEventSource.instance.emit("open"));
    store.dispatch.mockClear();
    act(() => vi.advanceTimersByTime(REALTIME_FALLBACK_MS));
    expect(store.dispatch).not.toHaveBeenCalled();
  });
});
