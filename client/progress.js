export function bindReadingProgress(element) {
  if (!element) return () => {};
  let frame = 0;
  const update = () => {
    frame = 0;
    const root = document.documentElement;
    const available = Math.max(0, root.scrollHeight - root.clientHeight);
    const ratio = available ? Math.min(1, Math.max(0, root.scrollTop / available)) : 0;
    element.style.transform = `scaleX(${ratio})`;
  };
  const requestUpdate = () => {
    if (!frame) frame = requestAnimationFrame(update);
  };
  update();
  window.addEventListener("scroll", requestUpdate, { passive: true });
  window.addEventListener("resize", requestUpdate);
  return () => {
    window.removeEventListener("scroll", requestUpdate);
    window.removeEventListener("resize", requestUpdate);
    if (frame) cancelAnimationFrame(frame);
  };
}
