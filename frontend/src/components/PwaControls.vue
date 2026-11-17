<script setup>
import { ref } from "vue";
import { Download, X, ArrowUpRight, RefreshCw, Smartphone } from "@lucide/vue";
import { useDialogFocus } from "../dialog.js";
import {
  installReady,
  installed,
  installApp,
  updateReady,
  applyUpdate,
} from "../pwa";
const help = ref(false);
const helpPanel = ref(null);
useDialogFocus(help, helpPanel, () => {
  help.value = false;
});
async function install() {
  if (installReady.value) await installApp();
  else help.value = true;
}
</script>
<template>
  <button v-if="updateReady" class="pwa-action" @click="applyUpdate">
    <RefreshCw :size="14" />Update app
  </button>
  <button v-else-if="!installed" class="pwa-action" @click="install">
    <Download :size="14" /><span>Install app</span>
  </button>
  <Teleport to="body"
    ><div v-if="help" class="modal-overlay" @click.self="help = false">
      <section
        ref="helpPanel"
        class="modal install-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Install Curbwatch"
      >
        <button
          class="modal-close icon-button"
          aria-label="Close installation help"
          @click="help = false"
        >
          <X :size="20" /></button
        ><span class="modal-icon"><Smartphone :size="26" /></span
        ><span class="eyebrow">YOUR OWN CURBWATCH APP</span>
        <h2>Keep it within reach.</h2>
        <p>
          Install Curbwatch to open it in its own window, with a home-screen
          icon.
        </p>
        <div class="install-steps">
          <strong>On this computer</strong>
          <p>
            Choose your browser’s install icon in the address bar, or look for
            “Install Curbwatch” in its menu.
          </p>
          <strong>On iPhone or iPad</strong>
          <p>Open the app in Safari, tap Share, then Add to Home Screen.</p>
          <strong>On Android</strong>
          <p>
            Open the app in Chrome and choose Install app or Add to Home screen
            from the menu.
          </p>
        </div>
        <div class="install-local-note">
          Use a trusted HTTPS address when opening this app on your phone. Ask
          your administrator for the deployed app address.
        </div>
        <button class="button primary full" @click="help = false">
          Got it<ArrowUpRight :size="15" />
        </button>
      </section>
    </div>
  </Teleport>
</template>
