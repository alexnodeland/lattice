/** What is wider than the page: an element past the window's right edge, outside any box that scrolls sideways. */
export function wider(): string[] {
  const scrolls = (element: Element | null): boolean =>
    element !== null &&
    element !== document.body &&
    (/auto|scroll/.test(getComputedStyle(element).overflowX) || scrolls(element.parentElement));
  return Array.from(document.body.querySelectorAll<HTMLElement>("*"))
    .filter((element) => {
      const box = element.getBoundingClientRect();
      return (
        (box.right > window.innerWidth + 1 || box.left < -1) &&
        box.width > 0 &&
        !scrolls(element.parentElement)
      );
    })
    .map(
      (element) => `${element.tagName.toLowerCase()}.${element.className.toString().slice(0, 60)}`,
    );
}
