import { ref, watch, onScopeDispose } from "vue";

export function useTimelinePlayback({
  hour,
  following,
  available = () => true,
  busy = () => false,
  schedule = setTimeout,
  cancel = clearTimeout,
  pageDocument = typeof document === "undefined" ? null : document,
}) {
  const playing = ref(false);
  const speed = ref(2000);
  let timer = null;

  function clear() {
    if (timer !== null) cancel(timer);
    timer = null;
  }
  function pause() {
    playing.value = false;
    clear();
  }
  function queue() {
    timer = schedule(() => {
      timer = null;
      if (!playing.value) return;
      if (!available() || pageDocument?.visibilityState === "hidden") {
        pause();
        return;
      }
      // Let the current map finish loading instead of skipping hourly views.
      if (!busy()) hour.value = (hour.value + 1) % 24;
      queue();
    }, speed.value);
  }
  function play() {
    if (
      playing.value ||
      !available() ||
      pageDocument?.visibilityState === "hidden"
    )
      return;
    following.value = false;
    playing.value = true;
    queue();
  }
  function toggle() {
    if (playing.value) pause();
    else play();
  }
  function setSpeed(value) {
    if (![1000, 2000].includes(value) || value === speed.value) return;
    speed.value = value;
    if (playing.value) {
      clear();
      queue();
    }
  }
  function visibilityChanged() {
    if (pageDocument.visibilityState === "hidden") pause();
  }
  watch(
    available,
    (allowed) => {
      if (!allowed) pause();
    },
    { flush: "sync" },
  );
  pageDocument?.addEventListener("visibilitychange", visibilityChanged);
  onScopeDispose(() => {
    pause();
    pageDocument?.removeEventListener("visibilitychange", visibilityChanged);
  });
  return { playing, speed, pause, toggle, setSpeed };
}
