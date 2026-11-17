<script setup>
import { runtime } from "./runtime";
import { ref, computed, watch, onMounted, onBeforeUnmount } from "vue";
import {
  LockKeyhole,
  Clock3,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  CircleHelp,
} from "@lucide/vue";
import HistoryPeriod from "./components/HistoryPeriod.vue";
import StreetMap from "./components/StreetMap.vue";
import TimelinePlayback from "./components/TimelinePlayback.vue";
import { useTimelinePlayback } from "./timeline/playback";
import { localNow, hourLabel } from "./api";
import { usePhoneLayout, useDialogFocus } from "./dialog.js";

const historyDays = ref(String(runtime.defaultHistoryDays));
const initial = localNow();
const day = ref(initial.day),
  hour = ref(initial.hour),
  following = ref(true);
const token = ref(location.hash.slice(1));
const activity = ref(null),
  roads = ref(null),
  selected = ref("");
const loading = ref(true),
  error = ref("");
let timer,
  request = 0;
const summary = computed(() =>
  activity.value?.streets.find(
    (street) => street.street_key === selected.value,
  ),
);
const phone = usePhoneLayout(),
  streetPanel = ref(null);
const streetSheetOpen = computed(() => phone.value && Boolean(summary.value));
useDialogFocus(streetSheetOpen, streetPanel, () => {
  selected.value = "";
});
const hourlyMax = computed(() =>
  Math.max(1, ...(activity.value?.hourly_counts || [])),
);
const {
  playing,
  speed,
  pause: pausePlayback,
  toggle: togglePlayback,
  setSpeed,
} = useTimelinePlayback({
  hour,
  following,
  available: () =>
    Boolean(activity.value && !error.value && !streetSheetOpen.value),
  busy: () => loading.value,
});
watch([day, token, historyDays], () => {
  pausePlayback();
  selected.value = "";
});
async function get(path) {
  const response = await fetch(`/api/shared/${path}`, {
    headers: { Authorization: `Bearer ${token.value}` },
    cache: "no-store",
    credentials: "omit",
    referrerPolicy: "no-referrer",
  });
  if (response.status === 404)
    throw new Error(
      "This map link is unavailable. It may have expired or been revoked. Ask the owner for a new link.",
    );
  if (!response.ok)
    throw new Error("The shared map could not be loaded. Please try again.");
  return response.json();
}
async function load() {
  if (!day.value) {
    day.value = localNow().day;
    return;
  }
  const currentRequest = ++request;
  loading.value = true;
  if (!/^[A-Za-z0-9_-]{43}$/.test(token.value)) {
    error.value =
      "Open the full map link from the owner, including the part after #.";
    activity.value = roads.value = null;
    loading.value = false;
    return;
  }
  try {
    const params = new URLSearchParams({
      day: day.value,
      hour: String(hour.value),
      history_days: historyDays.value,
    });
    const [result, streets] = await Promise.all([
      get(`activity?${params}`),
      roads.value || get("streets"),
    ]);
    if (currentRequest !== request) return;
    activity.value = result;
    if (
      selected.value &&
      !result.streets.some((street) => street.street_key === selected.value)
    )
      selected.value = "";
    roads.value = streets;
    error.value = "";
  } catch (failure) {
    if (currentRequest !== request) return;
    activity.value = roads.value = null;
    error.value =
      failure instanceof TypeError
        ? "The shared map could not be reached. Connect and try again."
        : failure.message;
  } finally {
    if (currentRequest === request) loading.value = false;
  }
}
function selectHour(value) {
  pausePlayback();
  following.value = false;
  hour.value = value;
}
function moveDay(amount) {
  pausePlayback();
  following.value = false;
  const current = new Date(`${day.value}T12:00:00Z`);
  current.setUTCDate(current.getUTCDate() + amount);
  day.value = current.toISOString().slice(0, 10);
}
function now() {
  pausePlayback();
  following.value = true;
  const current = localNow();
  day.value = current.day;
  hour.value = current.hour;
  load();
}
function refresh() {
  if (following.value) {
    const current = localNow();
    day.value = current.day;
    hour.value = current.hour;
  }
  load();
}
function hashChanged() {
  token.value = location.hash.slice(1);
  selected.value = "";
}
function visible() {
  if (document.visibilityState === "visible") refresh();
}
watch([day, hour, token, historyDays], () => {
  load();
});
onMounted(() => {
  load();
  timer = setInterval(() => {
    if (document.visibilityState === "visible") refresh();
  }, 60000);
  window.addEventListener("hashchange", hashChanged);
  document.addEventListener("visibilitychange", visible);
});
onBeforeUnmount(() => {
  request++;
  clearInterval(timer);
  window.removeEventListener("hashchange", hashChanged);
  document.removeEventListener("visibilitychange", visible);
});
</script>

<template>
  <div class="shared-page">
    <header class="shared-header">
      <div class="shared-brand"><span>P</span>curbwatch.</div>
      <span class="shared-readonly"
        ><LockKeyhole :size="14" />Shared map · Read only</span
      >
    </header>
    <div class="shared-intro">
      <div>
        <span class="eyebrow">A LITTLE LOCAL KNOWLEDGE</span>
        <h1>Street activity.</h1>
        <p>Explore parking ticket patterns in Syracuse, one hour at a time.</p>
      </div>
      <button
        class="button secondary"
        aria-label="Refresh map"
        :disabled="loading"
        @click="refresh"
      >
        <RefreshCw :size="18" :class="{ spin: loading }" /><span
          >Refresh map</span
        >
      </button>
    </div>
    <HistoryPeriod v-model="historyDays" :period="activity?.period" />
    <div
      v-if="activity && !activity.period.ticket_count"
      class="history-empty-note"
    >
      No verified tickets in this period. Choose a longer period or All history
      to include older tickets.
    </div>
    <div v-if="error" class="shared-error" role="alert">
      <LockKeyhole :size="23" />
      <h2>Map unavailable</h2>
      <p>{{ error }}</p>
      <button class="button secondary" @click="load">Try again</button>
    </div>
    <div v-else-if="!activity" class="shared-loading" role="status">
      Loading the shared map…
    </div>
    <div v-else class="map-workspace shared-workspace" :aria-busy="loading">
      <section class="map-panel">
        <StreetMap
          :activity="activity"
          :selected="selected"
          :street-data="roads"
          context-label="SHARED STREET ACTIVITY"
          empty-message="No street observations are available for this map yet."
          @select="selected = $event"
        />
        <div class="timeline-panel">
          <div class="timeline-heading">
            <div>
              <span class="eyebrow">EXPLORE BY HOUR</span
              ><strong
                >{{ hourLabel(hour) }} – {{ hourLabel((hour + 1) % 24)
                }}<small>{{ runtime.timezoneLabel }}</small></strong
              >
            </div>
            <div class="timeline-date">
              <input
                v-model="day"
                type="date"
                aria-label="Activity date"
                @change="following = false"
              />
              <button aria-label="Previous day" @click="moveDay(-1)">
                <ChevronLeft :size="17" />
              </button>
              <button class="now-button" :class="{ following }" @click="now">
                <span></span>Now
              </button>
              <button aria-label="Next day" @click="moveDay(1)">
                <ChevronRight :size="17" />
              </button>
            </div>
          </div>
          <TimelinePlayback
            :playing="playing"
            :speed="speed"
            :disabled="!activity || Boolean(error)"
            @toggle="togglePlayback"
            @speed="setSpeed"
          />
          <div class="hour-chart" role="group" aria-label="Choose an hour">
            <button
              v-for="h in 24"
              :key="h"
              :class="{ chosen: hour === h - 1 }"
              :aria-label="`Show ${hourLabel(h - 1)} activity`"
              :aria-pressed="hour === h - 1"
              @click="selectHour(h - 1)"
            >
              <span
                class="hour-bar"
                :style="{
                  height: `${6 + ((activity.hourly_counts[h - 1] || 0) / hourlyMax) * 34}px`,
                }"
              ></span>
              <span class="hour-label">{{
                (h - 1) % 3 === 0 || hour === h - 1 ? hourLabel(h - 1) : "·"
              }}</span>
            </button>
          </div>
          <input
            class="hour-slider"
            type="range"
            min="0"
            max="23"
            :value="hour"
            aria-label="Hour of day"
            @input="selectHour(Number($event.target.value))"
          />
          <div class="timeline-footer">
            <span
              >Bars show ticket counts in the selected period. Every ticket
              counts equally.</span
            ><span>12am — 11pm</span>
          </div>
        </div>
      </section>
      <div
        v-if="streetSheetOpen"
        class="street-sheet-backdrop"
        @click="selected = ''"
      ></div>
      <aside
        ref="streetPanel"
        class="street-panel"
        :class="{ 'street-sheet-open': streetSheetOpen }"
        :role="streetSheetOpen ? 'dialog' : undefined"
        :aria-modal="streetSheetOpen ? true : undefined"
        :aria-label="streetSheetOpen ? 'Street overview' : undefined"
        :tabindex="streetSheetOpen ? -1 : undefined"
      >
        <div class="street-panel-heading">
          <div>
            <h2>{{ summary ? "Street overview" : "Observed streets" }}</h2>
            <p>Activity around {{ hourLabel(hour) }}</p>
          </div>
          <button v-if="summary" class="text-button" @click="selected = ''">
            {{ phone ? "Close street details" : "All streets" }}
          </button>
        </div>
        <div v-if="summary" class="street-detail">
          <h2>{{ summary.name }}</h2>
          <span class="level-badge" :class="summary.level">{{
            summary.score === null ? "Limited data" : summary.level
          }}</span>
          <dl>
            <div>
              <dt>Exact-hour tickets</dt>
              <dd>{{ summary.sample_tickets }}</dd>
            </div>
            <div>
              <dt>Separate days</dt>
              <dd>{{ summary.distinct_days }}</dd>
            </div>
            <div>
              <dt>Ticketed days at this hour</dt>
              <dd>{{ summary.distinct_days }} / {{ summary.observed_days }}</dd>
            </div>
            <div>
              <dt>Tickets / observed day</dt>
              <dd>{{ summary.tickets_per_observed_day ?? "—" }}</dd>
            </div>
          </dl>
          <p class="detail-note">
            {{ summary.basis }}.
            {{
              summary.score === null
                ? "Fewer than three exact-hour tickets across two dates; shown as limited data."
                : "Color reflects the share of this street’s ticketed days with a ticket at this hour."
            }}
          </p>
        </div>
        <div v-else class="street-list">
          <button
            v-for="street in activity.streets"
            :key="street.street_key || street.name"
            class="street-row"
            @click="selected = street.street_key"
          >
            <span class="street-row-info"
              ><strong>{{ street.name }}</strong
              ><span>{{
                street.score === null
                  ? street.sample_tickets > 0
                    ? "Observed · limited data"
                    : "No exact-hour sample"
                  : `${street.level} activity`
              }}</span></span
            >
            <span class="activity-indicator" :class="street.level"
              ><i></i><i></i><i></i></span
            ><ChevronRight :size="14" />
          </button>
          <p v-if="!activity.streets.length" class="shared-empty">
            No street observations are available yet.
          </p>
        </div>
        <div class="street-panel-footer">
          <CircleHelp :size="17" />
          <p>
            Based on monitored cars.<br /><strong
              >Limited data doesn’t mean no enforcement.</strong
            >
          </p>
        </div>
      </aside>
    </div>
    <footer class="shared-footer">
      <Clock3 :size="15" />
      <p>
        Historical activity from the selected period. Colors summarize ticketed
        days, not the chance an officer is present. Vehicle and ticket records
        are private.
      </p>
    </footer>
  </div>
</template>
