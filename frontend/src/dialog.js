import { ref, nextTick, watch, onScopeDispose } from "vue";

const scrollLocks = new Set();
let bodyOverflow;
export const PHONE_QUERY =
  "(max-width: 740px), (max-width: 980px) and (max-height: 500px)";

export function usePhoneLayout() {
  const media = window.matchMedia(PHONE_QUERY);
  const phone = ref(media.matches);
  const change = () => {
    phone.value = media.matches;
  };
  media.addEventListener("change", change);
  onScopeDispose(() => media.removeEventListener("change", change));
  return phone;
}

export function useDialogFocus(open, element, close) {
  let previous,
    locked = false;
  const lock = Symbol("dialog");
  const focusable = () =>
    [
      ...(element.value?.querySelectorAll(
        'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), summary, [tabindex="0"]',
      ) || []),
    ].filter((item) => item.getClientRects().length);
  function release() {
    if (!locked) return;
    scrollLocks.delete(lock);
    if (!scrollLocks.size) document.body.style.overflow = bodyOverflow;
    locked = false;
    if (previous?.isConnected) previous.focus({ preventScroll: true });
  }
  function keyboard(event) {
    if (!open.value) return;
    const topDialog = [...document.querySelectorAll('[aria-modal="true"]')]
      .filter((dialog) => dialog.getClientRects().length)
      .at(-1);
    if (topDialog && topDialog !== element.value) return;
    if (event.key === "Escape") {
      if (
        element.value?.querySelector('[role="combobox"][aria-expanded="true"]')
      )
        return;
      event.preventDefault();
      event.stopImmediatePropagation();
      close();
    } else if (event.key === "Tab") {
      const items = focusable();
      const first = items[0] || element.value,
        last = items.at(-1) || first;
      if (
        event.shiftKey &&
        (document.activeElement === first ||
          !element.value?.contains(document.activeElement))
      ) {
        event.preventDefault();
        last?.focus();
      } else if (
        !event.shiftKey &&
        (document.activeElement === last ||
          !element.value?.contains(document.activeElement))
      ) {
        event.preventDefault();
        first?.focus();
      }
    }
  }
  watch(open, async (value) => {
    if (!value) {
      release();
      return;
    }
    previous = document.activeElement;
    if (!scrollLocks.size) bodyOverflow = document.body.style.overflow;
    scrollLocks.add(lock);
    locked = true;
    document.body.style.overflow = "hidden";
    await nextTick();
    if (open.value && !element.value?.contains(document.activeElement))
      (focusable()[0] || element.value)?.focus({ preventScroll: true });
  });
  document.addEventListener("keydown", keyboard, true);
  onScopeDispose(() => {
    release();
    document.removeEventListener("keydown", keyboard, true);
  });
}
