<script setup>
import { computed, onMounted, watch } from "vue";
import {
  MapPin,
  LocateFixed,
  ArrowRight,
  RefreshCw,
  ScanLine,
  CarFront,
  Plus,
  ReceiptText,
  CircleHelp,
  LoaderCircle,
} from "@lucide/vue";
import { api, localNow, hourLabel } from "../api";
import { runtime } from "../runtime";
import { online } from "../pwa";
import { useNearbyActivity } from "../location/current.js";

const props = defineProps({
  vehicles: { type: Number, default: 0 },
  tickets: { type: Number, default: 0 },
  checking: Boolean,
  version: { type: Number, default: 0 },
  shared: Boolean,
  loadActivity: { type: Function, default: api },
});
defineEmits(["street", "navigate", "scan", "check", "plate", "car"]);
const nearby = useNearbyActivity({
  load: props.loadActivity,
  clock: localNow,
  isOnline: () => online.value,
  clearOnError: props.shared,
});
const {
  data,
  loading,
  error,
  locationStatus,
  manualStreet,
  options,
  match,
  street,
  summary,
  stale,
  updatedAt,
  positionAt,
  current,
  locate,
  selectStreet,
  refresh,
} = nearby;
const locating = computed(() => locationStatus.value === "locating");
const state = computed(() =>
  locationStatus.value === "ready" ? match.value.status : locationStatus.value,
);
const messages = {
  idle: "Enable location to see historical ticket activity on your street, or choose a street below.",
  locating: "Finding your street. This can take a few seconds.",
  denied:
    "Location permission is off. Allow location in your browser’s site settings, or choose a street.",
  timeout:
    "Your phone took too long to find a location. Try again or choose a street.",
  unavailable: "Your location is unavailable. Try again or choose a street.",
  inaccurate:
    "The location is too approximate to pick a street reliably. Try outdoors or choose a street.",
  ambiguous:
    "You’re near more than one street. Choose the street you want to check.",
  outside:
    "No covered street was found close to this location. Coverage is currently limited to the configured Syracuse streets.",
  "no-geometry":
    "Street coverage is unavailable. Ask your administrator to load street geometry.",
  insecure:
    "Automatic location needs a secure HTTPS app address. You can still choose a street below.",
  unsupported: "This browser does not provide location. Choose a street below.",
};
const headline = computed(() => {
  if (!street.value)
    return locating.value ? "Finding your street…" : "Your street, right now.";
  if (!data.value)
    return loading.value ? "Loading activity…" : "Activity unavailable";
  if (!summary.value || summary.value.score === null)
    return summary.value?.sample_tickets ? "Limited data" : "Not enough data";
  return `${summary.value.level[0].toUpperCase()}${summary.value.level.slice(1)} activity`;
});
const level = computed(() =>
  !stale.value && summary.value?.score != null
    ? summary.value.level
    : "insufficient",
);
const explanation = computed(() => {
  if (!street.value) return messages[state.value] || "Loading street coverage…";
  if (!data.value)
    return error.value || "Looking at the last 90 days of verified tickets.";
  if (!summary.value?.sample_tickets)
    return "No verified tickets at this hour in the last 90 days on this street. That doesn’t mean there is no enforcement.";
  return `${summary.value.sample_tickets} tickets at this hour across ${summary.value.distinct_days} separate ${summary.value.distinct_days === 1 ? "day" : "days"}, in the last 90 days.`;
});
const time = (date) =>
  date
    ? new Intl.DateTimeFormat("en-US", {
        timeZone: runtime.timezone,
        hour: "numeric",
        minute: "2-digit",
      }).format(date)
    : "";
watch(
  () => props.version,
  () => refresh(),
);
onMounted(nearby.start);
</script>

<template>
  <div class="today-dashboard">
    <section
      class="nearby-card"
      :class="level"
      aria-labelledby="nearby-title"
      :aria-busy="locating || loading"
    >
      <div class="nearby-heading">
        <span class="eyebrow">{{
          manualStreet ? "YOUR SELECTED STREET" : "NEAR YOU"
        }}</span>
        <span class="nearby-hour"
          >{{ hourLabel(current.hour) }}–{{
            hourLabel((current.hour + 1) % 24)
          }}
          · {{ runtime.timezoneLabel }}</span
        >
      </div>
      <div class="nearby-street">
        <MapPin :size="18" /><span>{{
          street?.name || runtime.locationLabel
        }}</span>
      </div>
      <p class="nearby-label">Historical ticket activity</p>
      <div class="nearby-result" role="status" aria-live="polite">
        <h2 id="nearby-title">
          <LoaderCircle
            v-if="locating || (loading && !data)"
            class="spin"
            :size="24"
          />{{ headline }}
        </h2>
        <p>{{ explanation }}</p>
      </div>
      <p v-if="stale" class="nearby-warning" role="status">
        Saved activity · {{ error || "Connect to refresh this result." }}
      </p>
      <p v-else-if="error && !street" class="nearby-warning" role="alert">
        {{ error }}
      </p>
      <div class="nearby-actions">
        <button
          v-if="street && data"
          class="button primary"
          @click="$emit('street', street.key)"
        >
          View street<ArrowRight :size="17" />
        </button>
        <button
          v-if="!['insecure', 'unsupported'].includes(state)"
          class="button"
          :class="street ? 'secondary' : 'primary'"
          :disabled="locating"
          @click="locate"
        >
          <LocateFixed :size="17" />{{
            locating
              ? "Locating…"
              : street
                ? "Locate me"
                : state === "idle"
                  ? "Enable location"
                  : "Try location again"
          }}
        </button>
        <button
          v-if="error"
          class="button secondary"
          :disabled="loading || !online"
          @click="refresh()"
        >
          <RefreshCw :size="16" />Retry activity
        </button>
      </div>
      <div class="nearby-updated" v-if="updatedAt">
        {{
          loading
            ? "Refreshing activity…"
            : `Activity updated ${time(updatedAt)}`
        }}
      </div>
      <details
        class="street-picker"
        :open="state === 'ambiguous' && !manualStreet"
      >
        <summary>
          {{ manualStreet ? "Change street" : "Choose a street instead" }}
        </summary>
        <div v-if="state === 'ambiguous'" class="nearby-candidates">
          <button
            v-for="candidate in match.candidates.slice(0, 3)"
            :key="candidate.key"
            class="button secondary"
            @click="selectStreet(candidate.key)"
          >
            {{ candidate.name }}
          </button>
        </div>
        <label for="nearby-street">Street to check</label>
        <select
          id="nearby-street"
          :value="manualStreet"
          :disabled="!options.length"
          @change="selectStreet($event.target.value)"
        >
          <option value="" disabled>
            {{
              options.length
                ? "Select a covered street"
                : loading
                  ? "Loading streets…"
                  : "Street coverage unavailable"
            }}
          </option>
          <option
            v-for="option in options"
            :key="option.key"
            :value="option.key"
          >
            {{ option.name }}
          </option>
        </select>
      </details>
      <details class="nearby-evidence">
        <summary><CircleHelp :size="15" />What does this tell me?</summary>
        <p>
          This is historical activity from monitored plates, not a probability
          of getting a ticket or a live patrol report. It covers the whole
          street, not your exact block or side of the road.
        </p>
        <p v-if="summary">
          At this hour: {{ summary.distinct_days }} of
          {{ summary.observed_days }} ticketed days. A level needs at least
          three tickets across two dates. All weekdays count equally; days
          without recorded tickets are not known parking sessions.
        </p>
        <p v-if="positionAt && !manualStreet">
          Location checked {{ time(positionAt) }}. Tap Locate me if you have
          moved. Coordinates stay on this device.
        </p>
        <p v-else>Location is optional. Coordinates stay on this device.</p>
      </details>
    </section>

    <div v-if="!shared" class="today-totals">
      <button @click="$emit('navigate', 'cars')">
        <CarFront :size="21" /><span
          ><strong>{{ vehicles }}</strong> vehicles tracked</span
        ><ArrowRight :size="17" />
      </button>
      <button @click="$emit('navigate', 'tickets')">
        <ReceiptText :size="21" /><span
          ><strong>{{ tickets }}</strong> tickets recorded</span
        ><ArrowRight :size="17" />
      </button>
    </div>
    <section
      v-if="!shared"
      class="today-quick-actions"
      aria-labelledby="quick-actions-title"
    >
      <h2 id="quick-actions-title">Your garage</h2>
      <div>
        <button
          class="button primary"
          :disabled="!online"
          @click="$emit('plate')"
        >
          <Plus :size="19" />Quick add plate
        </button>
        <button
          class="button secondary"
          :disabled="!online"
          @click="$emit('car')"
        >
          <CarFront :size="19" />Add car
        </button>
        <button class="button secondary" @click="$emit('scan')">
          <ScanLine :size="19" />Scan a plate</button
        ><button
          class="button secondary"
          :disabled="checking || !online"
          @click="$emit('check')"
        >
          <RefreshCw :size="18" :class="{ spin: checking }" />{{
            checking ? "Checking plates…" : "Check tickets"
          }}
        </button>
      </div>
    </section>
  </div>
</template>

<style>
.today-dashboard {
  max-width: 900px;
}
.nearby-card {
  background: #eef3e6;
  border: 1px solid #dce6cf;
  border-radius: 18px;
  padding: 28px;
}
.nearby-heading {
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
}
.nearby-heading .eyebrow {
  color: #526b46;
  font-size: 11px;
}
.nearby-hour {
  color: #64745c;
  font-size: 12px;
}
.nearby-street {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: 24px 0 20px;
  font-size: 17px;
  font-weight: 550;
  overflow-wrap: anywhere;
}
.nearby-street svg {
  flex-shrink: 0;
  color: #647b50;
}
.nearby-label {
  font-size: 12px;
  color: #64745c;
  margin: 0 0 6px;
}
.nearby-result h2 {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  font-size: clamp(26px, 5vw, 36px);
  letter-spacing: -1px;
  font-weight: 550;
  line-height: 1.2;
  overflow-wrap: anywhere;
}
.nearby-card.low .nearby-result h2 {
  color: #32695e;
}
.nearby-card.moderate .nearby-result h2 {
  color: #80621b;
}
.nearby-card.high .nearby-result h2 {
  color: #9b492d;
}
.nearby-result p {
  max-width: 560px;
  color: #5e6f55;
  font-size: 14px;
  line-height: 1.65;
  margin: 14px 0 20px;
}
.nearby-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.nearby-actions .button {
  min-height: 44px;
  font-size: 13px;
}
.nearby-updated {
  margin-top: 12px;
  color: #64745c;
  font-size: 12px;
}
.nearby-warning {
  background: #fff5dc;
  border-radius: 8px;
  padding: 12px;
  font-size: 13px;
  line-height: 1.5;
}
.street-picker {
  margin-top: 18px;
}
.street-picker summary,
.nearby-evidence summary {
  cursor: pointer;
  font-size: 13px;
  color: #49633d;
  padding: 12px 0;
  min-height: 44px;
}
.street-picker label {
  display: block;
  font-size: 13px;
  margin: 8px 0;
}
.street-picker select {
  width: 100%;
  font-size: 16px;
  min-height: 46px;
  text-overflow: ellipsis;
}
.nearby-candidates {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.nearby-evidence {
  margin-top: 6px;
  border-top: 1px solid #d7e1ca;
}
.nearby-evidence summary {
  list-style-position: inside;
}
.nearby-evidence summary svg {
  vertical-align: middle;
  margin-right: 5px;
}
.nearby-evidence p {
  font-size: 13px;
  color: #5e6f55;
  line-height: 1.7;
  margin: 8px 0 12px;
}
.today-totals {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin: 20px 0 28px;
}
.today-totals button {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 12px;
  display: flex;
  align-items: center;
  padding: 20px;
  gap: 12px;
  text-align: left;
  color: #607353;
}
.today-totals button span {
  flex: 1;
  font-size: 13px;
}
.today-totals strong {
  display: block;
  font-size: 25px;
  color: var(--ink);
  margin-bottom: 3px;
}
.today-quick-actions h2 {
  font-size: 17px;
  font-weight: 550;
  margin: 0 0 14px;
}
.today-quick-actions > div {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.today-quick-actions .button {
  min-height: 48px;
  font-size: 14px;
}
@media (max-width: 740px), (max-width: 980px) and (max-height: 500px) {
  .nearby-card {
    padding: 20px;
    border-radius: 15px;
  }
  .nearby-street {
    margin: 20px 0 18px;
    font-size: 16px;
  }
  .nearby-heading {
    gap: 8px;
  }
  .nearby-hour {
    font-size: 11px;
  }
  .today-totals {
    gap: 10px;
    margin: 16px 0 26px;
  }
  .today-totals button {
    padding: 16px 12px;
    gap: 8px;
    align-items: start;
  }
  .today-totals button span {
    font-size: 12px;
    line-height: 1.5;
  }
  .today-totals button > svg:last-child {
    display: none;
  }
  .today-quick-actions > div {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .today-quick-actions .button {
    white-space: normal;
    padding: 10px;
    text-align: left;
  }
}
</style>
