const RESERVED_KEYS = new Set([
  "__proto__",
  "constructor",
  "prototype"
]);

const DEFAULT_STATE = {
  route: { view: "home" },
  bootstrap: null,
  project: null,
  loading: false,
  error: null
};

function stripPrivateFields(value) {
  if (Array.isArray(value)) return value.map(stripPrivateFields);
  if (!value || typeof value !== "object") return value;

  const clean = {};
  for (const [key, nestedValue] of Object.entries(value)) {
    const normalizedKey = key.replace(/[-_]/g, "").toLowerCase();
    const isPrivate = normalizedKey.startsWith("session")
      || normalizedKey.startsWith("provenance")
      || normalizedKey === "sourcelocator"
      || normalizedKey === "rawsession"
      || normalizedKey === "sourcepath";
    if (!RESERVED_KEYS.has(key) && !isPrivate) clean[key] = stripPrivateFields(nestedValue);
  }
  return clean;
}

function freezeTree(value) {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
  for (const nestedValue of Object.values(value)) freezeTree(nestedValue);
  return Object.freeze(value);
}

function normalizeState(value = {}) {
  return freezeTree(stripPrivateFields({ ...DEFAULT_STATE, ...value }));
}

export function createStore(initial = {}) {
  let state = normalizeState(initial);
  const listeners = new Set();

  function getState() {
    return state;
  }

  function setState(update) {
    const patch = typeof update === "function" ? update(state) : update;
    if (!patch || typeof patch !== "object" || Array.isArray(patch)) {
      throw new TypeError("state_update_object_required");
    }
    const previous = state;
    state = normalizeState({ ...state, ...patch });
    for (const listener of listeners) listener(state, previous);
    return state;
  }

  function subscribe(listener) {
    if (typeof listener !== "function") throw new TypeError("state_listener_required");
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  return Object.freeze({ getState, setState, subscribe });
}
