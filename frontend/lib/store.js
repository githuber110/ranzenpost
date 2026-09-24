export function createStore(target) {
  const listeners = new Set();

  const notify = (keys) => {
    for (const listener of [...listeners]) listener(keys);
  };

  const get = (key) => target[key];

  const set = (key, value) => {
    target[key] = value;
    notify([key]);
  };

  const patch = (partial) => {
    const keys = Object.keys(partial);
    for (const key of keys) target[key] = partial[key];
    notify(keys);
  };

  const subscribe = (listener) => {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  };

  return Object.freeze({ get, set, patch, subscribe });
}

export function storeGlobals() {
  return Object.freeze({ createStore });
}
