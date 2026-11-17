import { ref } from "vue";

export const online = ref(navigator.onLine);
export const installReady = ref(false);
export const updateReady = ref(false);
export const installed = ref(
  window.matchMedia("(display-mode: standalone)").matches ||
    navigator.standalone === true,
);
let installEvent, registration;

window.addEventListener("online", () => {
  online.value = true;
});
window.addEventListener("offline", () => {
  online.value = false;
});
window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  installEvent = event;
  installReady.value = true;
});
window.addEventListener("appinstalled", () => {
  installed.value = true;
  installReady.value = false;
  installEvent = null;
});

export async function installApp() {
  if (!installEvent) return false;
  await installEvent.prompt();
  const result = await installEvent.userChoice;
  installEvent = null;
  installReady.value = false;
  return result.outcome === "accepted";
}
export function applyUpdate() {
  registration?.waiting?.postMessage({ type: "SKIP_WAITING" });
}

export function registerPwa() {
  if (
    !("serviceWorker" in navigator) ||
    !window.isSecureContext ||
    import.meta.env.DEV
  )
    return;
  let reloading = false;
  const hadController = Boolean(navigator.serviceWorker.controller);
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (hadController && !reloading) {
      reloading = true;
      window.location.reload();
    }
  });
  navigator.serviceWorker
    .register("/sw.js", { scope: "/" })
    .then((reg) => {
      registration = reg;
      updateReady.value = Boolean(reg.waiting);
      reg.addEventListener("updatefound", () => {
        reg.installing?.addEventListener("statechange", () => {
          updateReady.value = Boolean(
            reg.waiting && navigator.serviceWorker.controller,
          );
        });
      });
    })
    .catch((error) =>
      console.warn("PWA installation is unavailable:", error.message),
    );
}
