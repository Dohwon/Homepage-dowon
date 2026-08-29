function decodeSectionHash(hash) {
  if (typeof hash !== "string" || !hash.startsWith("#") || hash.length < 2) return null;
  try {
    return decodeURIComponent(hash.slice(1)) || null;
  } catch {
    return null;
  }
}

function readerSections(root) {
  return [...(root?.querySelectorAll?.("[data-article-section]") || [])];
}

function sectionForHash(root, hash) {
  const id = decodeSectionHash(hash);
  if (!id) return null;
  return readerSections(root).find((section) => section.id === id) || null;
}

export function hasValidProjectHash(root, hash) {
  return Boolean(sectionForHash(root, hash));
}

export function shouldResetProjectScroll(root, hash) {
  return !hasValidProjectHash(root, hash);
}

export function bindProjectReader(root, {
  observerFactory = (callback) => new IntersectionObserver(callback, {
    rootMargin: "-24% 0px -64%",
    threshold: [0, 1]
  }),
  history = globalThis.history,
  location = globalThis.location,
  windowTarget = globalThis.window,
  requestFrame = (callback) => requestAnimationFrame(callback),
  cancelFrame = (frame) => cancelAnimationFrame(frame)
} = {}) {
  const sections = readerSections(root);
  if (!sections.length) return () => {};

  const links = new Map();
  for (const link of root.querySelectorAll("[data-project-toc] a[href^='#']")) {
    const id = decodeSectionHash(link.getAttribute("href"));
    if (!id) continue;
    if (!links.has(id)) links.set(id, []);
    links.get(id).push(link);
  }

  let disposed = false;
  const activate = (id, { updateHash = true } = {}) => {
    if (disposed) return;
    for (const [linkId, matchingLinks] of links) {
      for (const link of matchingLinks) {
        if (linkId === id) link.setAttribute("aria-current", "location");
        else link.removeAttribute("aria-current");
      }
    }
    if (!updateHash || !history || !location) return;
    const nextHash = `#${encodeURIComponent(id)}`;
    if (location.hash === nextHash) return;
    history.replaceState(history.state, "", `${location.pathname}${location.search}${nextHash}`);
  };

  let restoreFrame = 0;
  let preserveInitialHash = hasValidProjectHash(root, location?.hash);
  const restoreHash = () => {
    restoreFrame = 0;
    if (disposed) return;
    const section = sectionForHash(root, location?.hash);
    if (!section) {
      preserveInitialHash = false;
      return;
    }
    activate(section.id, { updateHash: false });
    section.scrollIntoView({ block: "start" });
    preserveInitialHash = false;
  };
  const scheduleHashRestore = () => {
    if (disposed) return;
    if (restoreFrame) cancelFrame(restoreFrame);
    restoreFrame = requestFrame(restoreHash);
  };

  const observer = observerFactory((entries) => {
    if (disposed || preserveInitialHash) return;
    const current = entries
      .filter((entry) => entry.isIntersecting && entry.target?.id)
      .sort((left, right) => left.boundingClientRect.top - right.boundingClientRect.top)[0];
    if (current) activate(current.target.id);
  });
  sections.forEach((section) => observer.observe(section));

  const onHashChange = () => scheduleHashRestore();
  windowTarget?.addEventListener?.("hashchange", onHashChange);
  scheduleHashRestore();

  return () => {
    if (disposed) return;
    disposed = true;
    observer.disconnect();
    windowTarget?.removeEventListener?.("hashchange", onHashChange);
    if (restoreFrame) cancelFrame(restoreFrame);
  };
}
