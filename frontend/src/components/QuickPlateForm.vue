<script setup>
import { ref, onMounted, nextTick, watch } from "vue";
import { Plus, X, LoaderCircle, CircleAlert } from "@lucide/vue";
import SelectMenu from "./SelectMenu.vue";
import plateStates from "../plate-states.json";
import { api } from "../api";
import { online } from "../pwa";
import { normalizePlate } from "../scanner/candidates";
import { useDialogFocus } from "../dialog.js";

const emit = defineEmits(["close", "saved"]);
const panel = ref(null),
  plateInput = ref(null);
const plate = ref(""),
  state = ref("NY"),
  saving = ref(false);
const error = ref(""),
  message = ref("");
watch([plate, state], () => {
  error.value = "";
});
const options = Object.entries(plateStates)
  .map(([value, name]) => ({ value, label: `${name} (${value})` }))
  .sort((a, b) => a.label.localeCompare(b.label));
function close() {
  if (!saving.value) emit("close");
}
const open = ref(false);
useDialogFocus(open, panel, close);
onMounted(async () => {
  open.value = true;
  await nextTick();
  plateInput.value?.focus();
});
async function save(addMore) {
  if (saving.value || !online.value) return;
  error.value = message.value = "";
  const normalized = normalizePlate(plate.value);
  if (!/^[A-Z0-9]{1,10}$/.test(normalized)) {
    error.value = "Enter 1–10 letters or numbers for the license plate.";
    plateInput.value?.focus();
    return;
  }
  plate.value = normalized;
  saving.value = true;
  try {
    const result = await api("/plates", {
      method: "POST",
      body: { plate: normalized, plate_state: state.value },
    });
    emit("saved", result, { addMore });
    if (addMore) {
      plate.value = "";
      state.value = "NY";
      message.value = `${result.plate} added. Ready for the next plate.`;
    } else emit("close");
  } catch (failure) {
    error.value = failure.message;
  } finally {
    saving.value = false;
    if (addMore) {
      await nextTick();
      plateInput.value?.focus();
    }
  }
}
</script>

<template>
  <div class="modal-overlay" @click.self="close">
    <section
      ref="panel"
      class="modal quick-plate-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="quick-plate-title"
    >
      <button
        class="modal-close icon-button"
        aria-label="Close quick add plate"
        :disabled="saving"
        @click="close"
      >
        <X :size="20" />
      </button>
      <span class="modal-icon"><Plus :size="26" /></span>
      <span class="eyebrow">BUILD THE STREET HISTORY</span>
      <h2 id="quick-plate-title">Quick add plate.</h2>
      <p>
        Add a plate to collect ticket data, without owner details or emails.
      </p>
      <form @submit.prevent="save($event.submitter?.value === 'more')">
        <label for="quick-plate">License plate</label>
        <input
          id="quick-plate"
          ref="plateInput"
          v-model="plate"
          class="plate-input"
          placeholder="ABC1234"
          maxlength="18"
          required
          autocomplete="off"
          autocapitalize="characters"
          spellcheck="false"
          :disabled="saving"
        />
        <label for="quick-plate-state">Plate state</label>
        <SelectMenu
          id="quick-plate-state"
          v-model="state"
          label="Plate state"
          :options="options"
          :disabled="saving"
        />
        <span class="field-hint"
          >Check the plate text before saving. Plates with no tickets are still
          monitored.</span
        >
        <div v-if="error" class="form-error" role="alert">
          <CircleAlert :size="16" />{{ error }}
        </div>
        <p v-if="message" class="quick-plate-success" role="status">
          {{ message }}
        </p>
        <p v-if="!online" class="form-error" role="status">
          Connect to add this plate.
        </p>
        <div class="modal-actions">
          <button
            class="button secondary"
            type="submit"
            value="exit"
            :disabled="saving || !online"
          >
            Save & exit
          </button>
          <button
            class="button primary"
            type="submit"
            value="more"
            :disabled="saving || !online"
          >
            <LoaderCircle v-if="saving" :size="16" class="spin" /><Plus
              v-else
              :size="16"
            />{{ saving ? "Checking & saving…" : "Save & add more" }}
          </button>
        </div>
      </form>
      <div class="modal-note">
        <CircleAlert :size="15" />Ticket lookup runs before saving. Syracuse
        searches by plate text without a state filter.
      </div>
    </section>
  </div>
</template>

<style>
.quick-plate-success {
  color: #32695e;
  font-size: 14px;
}
.quick-plate-modal .modal-actions {
  flex-wrap: wrap;
}
.quick-plate-modal .modal-actions .button {
  flex: 1;
  min-height: 46px;
}
</style>
