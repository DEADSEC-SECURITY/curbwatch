<script setup>
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from "vue";
import {
  Share2,
  X,
  Copy,
  Check,
  LoaderCircle,
  ExternalLink,
  Link2,
  ChevronLeft,
  ChevronRight,
} from "@lucide/vue";
import { api, dateTime } from "../api";
import SelectMenu from "./SelectMenu.vue";
import { useDialogFocus } from "../dialog.js";

const expiryOptions = [
  { value: "7", label: "7 days" },
  { value: "30", label: "30 days" },
  { value: "never", label: "No expiry" },
];

const emit = defineEmits(["close"]);
const links = ref([]),
  name = ref("Map link"),
  expiry = ref("30");
const busy = ref(false),
  error = ref(""),
  created = ref(null),
  copied = ref(false);
const localOnly = ref(true),
  revoking = ref("");
const linkInput = ref(null);
const dialogPanel = ref(null),
  dialogOpen = ref(false);
useDialogFocus(dialogOpen, dialogPanel, () => emit("close"));
const linkPage = ref(0),
  pageSize = ref(window.innerHeight < 820 ? 2 : 4);
const pageCount = computed(() =>
  Math.max(1, Math.ceil(links.value.length / pageSize.value)),
);
const visibleLinks = computed(() =>
  links.value.slice(
    linkPage.value * pageSize.value,
    (linkPage.value + 1) * pageSize.value,
  ),
);
function resize() {
  pageSize.value = window.innerHeight < 820 ? 2 : 4;
  linkPage.value = Math.min(linkPage.value, pageCount.value - 1);
}
async function load() {
  const data = await api("/shares");
  links.value = data.links;
  localOnly.value = data.local_only;
  linkPage.value = Math.min(linkPage.value, pageCount.value - 1);
}
async function create() {
  busy.value = true;
  error.value = "";
  try {
    created.value = await api("/shares", {
      method: "POST",
      body: {
        name: name.value,
        expires_in_days: expiry.value === "never" ? null : Number(expiry.value),
      },
    });
    copied.value = false;
    linkPage.value = 0;
    await nextTick();
    linkInput.value?.focus({ preventScroll: true });
    linkInput.value?.scrollIntoView({ block: "nearest" });
    await load();
  } catch (failure) {
    error.value = failure.message;
  } finally {
    busy.value = false;
  }
}
async function copy() {
  try {
    await navigator.clipboard.writeText(created.value.url);
    copied.value = true;
  } catch {
    linkInput.value?.focus();
    linkInput.value?.select();
    error.value = "Copy the selected link using your browser’s copy command.";
  }
}
async function revoke(link) {
  revoking.value = link.id;
  error.value = "";
  try {
    await api(`/shares/${link.id}/revoke`, { method: "POST" });
    if (created.value?.id === link.id) created.value = null;
    await load();
  } catch (failure) {
    error.value = failure.message;
  } finally {
    revoking.value = "";
  }
}
onMounted(async () => {
  dialogOpen.value = true;
  window.addEventListener("resize", resize);
  try {
    await load();
  } catch (failure) {
    error.value = failure.message;
  }
});
onBeforeUnmount(() => {
  window.removeEventListener("resize", resize);
});
</script>

<template>
  <div class="modal-overlay" @click.self="emit('close')">
    <section
      ref="dialogPanel"
      class="modal share-dialog"
      role="dialog"
      aria-modal="true"
      aria-label="Share map"
    >
      <button
        class="modal-close icon-button"
        aria-label="Close sharing"
        @click="emit('close')"
      >
        <X :size="20" />
      </button>
      <header class="share-header">
        <span class="modal-icon"><Share2 :size="26" /></span>
        <div>
          <span class="eyebrow">A VIEW YOU CAN SHARE</span>
          <h2>Share your map.</h2>
          <p>
            Only the map and timeline are shared. Plates, contact details and
            individual tickets stay private.
          </p>
        </div>
      </header>
      <div class="share-dialog-body">
        <div class="share-layout">
          <section class="share-setup" aria-label="Create a map link">
            <div v-if="localOnly" class="share-local-note">
              Local preview: links work on this computer only.
            </div>
            <form class="share-create" @submit.prevent="create">
              <label for="share-name">Link name <span>(for you)</span></label>
              <input
                id="share-name"
                v-model="name"
                maxlength="80"
                autocomplete="off"
              />
              <label for="share-expiry">Expires after</label>
              <SelectMenu
                id="share-expiry"
                v-model="expiry"
                label="Expires after"
                :options="expiryOptions"
              />
              <button class="button primary" type="submit" :disabled="busy">
                <LoaderCircle v-if="busy" class="spin" :size="16" /><Share2
                  v-else
                  :size="16"
                />{{ busy ? "Creating…" : "Create link" }}
              </button>
            </form>
            <div v-if="error" class="share-error" role="alert">{{ error }}</div>
          </section>
          <section
            class="share-preview"
            :class="{ 'share-preview-empty': !created }"
            aria-label="Link preview"
          >
            <div v-if="created" class="share-result">
              <label for="new-share-url">Your read-only map link</label>
              <input
                id="new-share-url"
                ref="linkInput"
                :value="created.url"
                readonly
                @focus="$event.target.select()"
              />
              <div class="share-result-actions">
                <button class="button primary" @click="copy">
                  <Check v-if="copied" :size="16" /><Copy v-else :size="16" />{{
                    copied ? "Copied" : "Copy link"
                  }}
                </button>
                <a
                  class="button secondary"
                  :href="created.url"
                  target="_blank"
                  rel="noopener noreferrer"
                  >Open preview<ExternalLink :size="15"
                /></a>
              </div>
              <p role="status">
                Copy this link now. Its full address is shown only when created.
              </p>
            </div>
            <div v-else class="share-empty-preview">
              <Link2 :size="25" />
              <strong>Your link will appear here.</strong>
              <p>Create a link, then copy it or open a preview.</p>
            </div>
          </section>
        </div>
        <div class="share-link-list">
          <h3>
            Your map links <span>{{ links.length }}</span>
          </h3>
          <p v-if="!links.length">
            No links yet. Create one to preview the shared map.
          </p>
          <div class="share-link-grid">
            <article
              v-for="link in visibleLinks"
              :key="link.id"
              class="share-link-row"
            >
              <div>
                <strong>{{ link.name }}</strong><span>{{
                  link.status === "active"
                    ? link.expires_at
                      ? `Expires ${dateTime(link.expires_at)}`
                      : "No expiry"
                    : link.status
                }}</span>
              </div>
              <button
                v-if="link.status === 'active'"
                class="button secondary"
                :disabled="Boolean(revoking)"
                :aria-label="`Revoke ${link.name}`"
                @click="revoke(link)"
              >
                {{ revoking === link.id ? "Revoking…" : "Revoke" }}
              </button>
              <span v-else class="share-status">{{ link.status }}</span>
            </article>
          </div>
          <div
            v-if="pageCount > 1"
            class="share-pagination"
            role="group"
            aria-label="Map link pages"
          >
            <span role="status"
              >Page {{ linkPage + 1 }} of {{ pageCount }}</span
            >
            <button
              class="button secondary"
              :disabled="linkPage === 0"
              aria-label="Previous link page"
              @click="linkPage = Math.max(0, linkPage - 1)"
            >
              <ChevronLeft :size="15" />Previous
            </button>
            <button
              class="button secondary"
              :disabled="linkPage >= pageCount - 1"
              aria-label="Next link page"
              @click="linkPage = Math.min(pageCount - 1, linkPage + 1)"
            >
              Next<ChevronRight :size="15" />
            </button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
