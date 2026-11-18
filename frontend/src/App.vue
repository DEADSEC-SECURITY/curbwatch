<script setup>
import { runtime } from "./runtime";
import {
  ref,
  computed,
  onMounted,
  onBeforeUnmount,
  watch,
  nextTick,
} from "vue";
import {
  Map as MapIcon,
  CarFront,
  ReceiptText,
  Plus,
  ArrowUpRight,
  ArrowRight,
  ChevronRight,
  Search,
  Clock3,
  X,
  RefreshCw,
  LocateFixed,
  Pause,
  Play,
  Check,
  Upload,
  CircleAlert,
  CircleCheck,
  MapPin,
  Route,
  CircleHelp,
  Pencil,
  CalendarDays,
  ChevronLeft,
  LoaderCircle,
  ScanLine,
  WifiOff,
  Share2,
  Settings as SettingsIcon,
  LogOut,
  House,
  Ellipsis,
} from "@lucide/vue";
import HistoryPeriod from "./components/HistoryPeriod.vue";
import Settings from "./components/Settings.vue";
import TodayDashboard from "./components/TodayDashboard.vue";
import { usePhoneLayout, useDialogFocus } from "./dialog.js";

const props = defineProps({ user: { type: Object, required: true } });
const emit = defineEmits(["logout", "session"]);

import StreetMap from "./components/StreetMap.vue";
import PlateScanner from "./components/PlateScanner.vue";
import QuickPlateForm from "./components/QuickPlateForm.vue";
import PwaControls from "./components/PwaControls.vue";
import ShareLinks from "./components/ShareLinks.vue";
import TimelinePlayback from "./components/TimelinePlayback.vue";
import { useTimelinePlayback } from "./timeline/playback";
import SelectMenu from "./components/SelectMenu.vue";
import plateStates from "./plate-states.json";
import { online } from "./pwa";
import { normalizePlate } from "./scanner/candidates";
import { api, money, dateTime, shortDate, hourLabel, localNow } from "./api";

const historyDays = ref(String(runtime.defaultHistoryDays));
const draftKey = `curbwatch-vehicle-draft-${props.user.id}`;
const initial = localNow();
const phone = usePhoneLayout();
const validPages = ["today", "map", "cars", "tickets", "settings"];
const page = ref(
  validPages.includes(location.hash.slice(1))
    ? location.hash.slice(1)
    : phone.value
      ? "today"
      : "map",
);
const mobileMenu = ref(false),
  menuPanel = ref(null),
  streetPanel = ref(null);
const activityVersion = ref(0);
const cars = ref([]),
  tickets = ref([]),
  stats = ref({}),
  runs = ref([]),
  activity = ref(null);
const day = ref(initial.day),
  hour = ref(initial.hour),
  followNow = ref(true),
  ticketCar = ref("");
const selectedStreet = ref(""),
  search = ref(""),
  streetSearch = ref(""),
  mapRef = ref(null);
const loading = ref(true),
  activityLoading = ref(false),
  connectionError = ref(""),
  submittingCheck = ref(false);
const modal = ref(null),
  formError = ref(""),
  saving = ref(false),
  nameInput = ref(null);
const form = ref({ name: "", plate: "", email: "", plate_state: "" }),
  editing = ref(null);
const scannerOpen = ref(false),
  scanPreview = ref(""),
  lookup = ref(null),
  lookupBusy = ref(false),
  confirmNoTickets = ref(false);
const sharingOpen = ref(false);
const quickPlateOpen = ref(false),
  recordFilter = ref("vehicle");
const plateStateOptions = [
  { value: "", label: "Not set" },
  ...Object.entries(plateStates)
    .map(([value, name]) => ({ value, label: `${name} (${value})` }))
    .sort((a, b) => a.label.localeCompare(b.label)),
];
const plateLabel = (car) =>
  `${car.plate}${car.plate_state ? ` · ${car.plate_state}` : ""}`;
const snapshotAt = ref(null),
  showingSnapshot = ref(false);
const importCar = ref(""),
  importFile = ref(null),
  importFilename = ref("");
const toast = ref(null),
  detailTicket = ref(null),
  modalPanel = ref(null),
  ticketPanel = ref(null);
let interval,
  toastTimer,
  activityRequest = 0,
  lastFinishedRun,
  refreshing = false;
let lookupRequest = 0,
  disposed = false;

const busyRun = computed(() =>
  runs.value.find((r) => ["queued", "running"].includes(r.status)),
);
const checking = computed(
  () => Boolean(busyRun.value) || submittingCheck.value,
);
const title = computed(
  () =>
    ({
      today: "Today",
      map: "Street activity",
      cars: "Cars & plates",
      tickets: "Ticket history",
      settings: "Settings",
    })[page.value],
);
const filteredCars = computed(() =>
  cars.value.filter(
    (c) =>
      (!recordFilter.value ||
        (c.record_type || "vehicle") === recordFilter.value) &&
      `${c.name} ${c.plate} ${c.plate_state || ""} ${plateStates[c.plate_state] || ""}`
        .toLowerCase()
        .includes(search.value.toLowerCase()),
  ),
);
const filteredTickets = computed(() =>
  tickets.value.filter(
    (t) =>
      (!ticketCar.value || t.car_id === Number(ticketCar.value)) &&
      `${t.ticket_number} ${t.location_name} ${t.plate} ${t.plate_state || ""} ${t.description}`
        .toLowerCase()
        .includes(search.value.toLowerCase()),
  ),
);
const streetList = computed(() =>
  (activity.value?.streets || []).filter((s) =>
    s.name.toLowerCase().includes(streetSearch.value.toLowerCase()),
  ),
);
const selectedSummary = computed(() =>
  activity.value?.streets?.find((s) => s.street_key === selectedStreet.value),
);
const streetSheetOpen = computed(
  () => phone.value && Boolean(selectedSummary.value),
);
useDialogFocus(mobileMenu, menuPanel, () => {
  mobileMenu.value = false;
});
useDialogFocus(streetSheetOpen, streetPanel, () => {
  selectedStreet.value = "";
});
useDialogFocus(
  computed(() => Boolean(modal.value)),
  modalPanel,
  () => {
    modal.value = null;
  },
);
useDialogFocus(
  computed(() => Boolean(detailTicket.value)),
  ticketPanel,
  () => {
    detailTicket.value = null;
  },
);
watch(phone, () => {
  mobileMenu.value = false;
});
const hourlyMax = computed(() =>
  Math.max(1, ...(activity.value?.hourly_counts || [])),
);
const selectedDayLabel = computed(() =>
  new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${day.value}T12:00:00Z`)),
);
const hourRange = computed(
  () => `${hourLabel(hour.value)} – ${hourLabel((hour.value + 1) % 24)}`,
);
const activeCount = computed(() => cars.value.filter((c) => c.active).length);
const vehicleCount = computed(
  () => cars.value.filter((c) => c.record_type !== "plate").length,
);
const plateCount = computed(() => cars.value.length - vehicleCount.value);
const lastErrors = computed(
  () => runs.value.find((r) => r.errors?.length)?.errors || [],
);
const evidenceCount = computed(
  () => activity.value?.streets?.filter((s) => s.score !== null).length || 0,
);
const {
  playing,
  speed,
  pause: pausePlayback,
  toggle: togglePlayback,
  setSpeed,
} = useTimelinePlayback({
  hour,
  following: followNow,
  available: () =>
    Boolean(
      page.value === "map" &&
      activity.value &&
      online.value &&
      !showingSnapshot.value &&
      !connectionError.value &&
      !modal.value &&
      !mobileMenu.value &&
      !streetSheetOpen.value &&
      !sharingOpen.value &&
      !scannerOpen.value &&
      !quickPlateOpen.value,
    ),
  busy: () => activityLoading.value,
});
watch([day, historyDays], () => {
  pausePlayback();
  selectedStreet.value = "";
});

function navigate(value) {
  mobileMenu.value = false;
  page.value = value;
  location.hash = value;
  search.value = "";
  selectedStreet.value = "";
}
function hashChanged() {
  const value = location.hash.slice(1);
  if (validPages.includes(value) && value !== page.value) {
    page.value = value;
    search.value = "";
    selectedStreet.value = "";
    mobileMenu.value = false;
  }
}
async function viewNearbyStreet(key) {
  navigate("map");
  jumpNow();
  await loadActivity();
  if (page.value === "map") selectedStreet.value = key;
}
function notify(message, kind = "success") {
  toast.value = { message, kind };
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.value = null;
  }, 6500);
}
async function loadActivity() {
  const request = ++activityRequest;
  activityLoading.value = true;
  const params = new URLSearchParams({
    day: day.value,
    hour: String(hour.value),
    history_days: historyDays.value,
  });
  try {
    const data = await api(`/activity?${params}`);
    if (request === activityRequest) {
      activity.value = data;
      if (
        selectedStreet.value &&
        !data.streets.some(
          (street) => street.street_key === selectedStreet.value,
        )
      )
        selectedStreet.value = "";
    }
  } catch (error) {
    if (request === activityRequest) connectionError.value = error.message;
  } finally {
    if (request === activityRequest) activityLoading.value = false;
  }
}
async function refresh(full = false) {
  if (refreshing) return;
  refreshing = true;
  try {
    const [newCars, overview, checks] = await Promise.all([
      api("/cars"),
      api("/overview"),
      api("/checks"),
    ]);
    cars.value = newCars;
    stats.value = overview;
    runs.value = checks;
    connectionError.value = "";
    showingSnapshot.value = false;
    const finished = checks.find(
      (r) => !["queued", "running"].includes(r.status),
    );
    const finishedId = finished?.id ?? null;
    if (full || finishedId !== lastFinishedRun) {
      tickets.value = await api("/tickets");
      await loadActivity();
      activityVersion.value++;
      if (!full && finished && lastFinishedRun !== undefined) {
        if (finished.status === "completed")
          notify(
            `Check complete. ${finished.new_tickets} new ${finished.new_tickets === 1 ? "ticket" : "tickets"}, ${finished.updated_tickets} updated.`,
          );
        else
          notify(
            finished.errors?.[0] || "Some vehicles could not be checked.",
            "error",
          );
      }
      lastFinishedRun = finishedId;
    }
    snapshotAt.value = new Date().toISOString();
  } catch (error) {
    connectionError.value = error.message;
    showingSnapshot.value = Boolean(snapshotAt.value);
  } finally {
    refreshing = false;
    loading.value = false;
  }
}
async function checkTickets(carId = null) {
  if (!online.value) {
    notify("Connect to run a ticket check.", "error");
    return;
  }
  submittingCheck.value = true;
  try {
    await api("/checks", { method: "POST", body: { car_id: carId } });
    await refresh();
    notify(
      carId
        ? "Checking this vehicle’s ticket history…"
        : "Checking your tracked plates…",
    );
  } catch (error) {
    notify(error.message, "error");
  } finally {
    submittingCheck.value = false;
  }
}
function plateSaved(result, { addMore }) {
  recordFilter.value = "plate";
  if (!addMore) notify(`${result.plate} added for data collection.`);
  refresh(true);
}
function openCar(car = null) {
  editing.value = car;
  form.value = {
    name: car?.name || "",
    plate: car?.plate || "",
    email: car?.email || "",
    plate_state: car?.plate_state || "",
  };
  formError.value = "";
  lookupRequest++;
  lookupBusy.value = false;
  lookup.value = null;
  confirmNoTickets.value = false;
  scanPreview.value = "";
  modal.value = "car";
  nextTick(() => nameInput.value?.focus());
}
function chooseScannedPlate(result) {
  scannerOpen.value = false;
  openCar();
  form.value.plate = result.plate;
  scanPreview.value = result.thumbnail || "";
}
function enterPlateManually() {
  scannerOpen.value = false;
  openCar();
}
async function lookupPlate() {
  formError.value = "";
  lookup.value = null;
  confirmNoTickets.value = false;
  if (!online.value) {
    formError.value = "Connect to check tickets before adding this plate.";
    return;
  }
  const plate = normalizePlate(form.value.plate);
  if (!/^[A-Z0-9]{1,10}$/.test(plate)) {
    formError.value = "Enter 1–10 letters or numbers for the license plate.";
    return;
  }
  form.value.plate = plate;
  const request = ++lookupRequest;
  lookupBusy.value = true;
  try {
    const result = await api("/plate-lookups", {
      method: "POST",
      body: { plate, plate_state: form.value.plate_state },
    });
    if (
      request === lookupRequest &&
      modal.value === "car" &&
      normalizePlate(form.value.plate) === plate
    )
      lookup.value = result;
  } catch (error) {
    if (request === lookupRequest) formError.value = error.message;
  } finally {
    if (request === lookupRequest) lookupBusy.value = false;
  }
}
async function saveCar() {
  if (!editing.value && !lookup.value) {
    await lookupPlate();
    return;
  }
  formError.value = "";
  saving.value = true;
  try {
    const result = await api(
      editing.value ? `/cars/${editing.value.id}` : "/cars",
      {
        method: editing.value ? "PATCH" : "POST",
        body: editing.value
          ? {
              name: form.value.name,
              email: form.value.email,
              plate_state: form.value.plate_state,
              record_type: "vehicle",
            }
          : {
              ...form.value,
              lookup_id: lookup.value.id,
              confirm_no_tickets: confirmNoTickets.value,
            },
      },
    );
    const isNew = !editing.value;
    modal.value = null;
    recordFilter.value = "vehicle";
    await refresh(true);
    notify(
      isNew
        ? `${result.plate} is now being tracked.`
        : "Vehicle details updated.",
    );
  } catch (error) {
    formError.value = error.message;
  } finally {
    saving.value = false;
  }
}
async function toggleCar(car) {
  if (!online.value) {
    notify("Connect to change vehicle monitoring.", "error");
    return;
  }
  try {
    await api(`/cars/${car.id}`, {
      method: "PATCH",
      body: { active: !car.active },
    });
    await refresh();
    notify(
      car.active
        ? `${car.plate} paused. Its history is saved.`
        : `${car.plate} monitoring resumed.`,
    );
  } catch (error) {
    notify(error.message, "error");
  }
}
function selectHour(value) {
  pausePlayback();
  hour.value = value;
  followNow.value = false;
}
function jumpNow() {
  pausePlayback();
  const now = localNow();
  day.value = now.day;
  hour.value = now.hour;
  followNow.value = true;
}
function moveDay(delta) {
  pausePlayback();
  const date = new Date(`${day.value}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + delta);
  day.value = date.toISOString().slice(0, 10);
  followNow.value = false;
}
function showStreetTickets(key) {
  navigate("tickets");
  search.value = key;
}
function openImport() {
  modal.value = "import";
  formError.value = "";
  importFile.value = null;
  importFilename.value = "";
  importCar.value = "";
}
async function readImport(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  if (file.size > 5_000_000) {
    formError.value = "Please choose a file smaller than 5 MB.";
    return;
  }
  importFile.value = await file.text();
  importFilename.value = file.name;
  formError.value = "";
}
async function submitImport() {
  saving.value = true;
  formError.value = "";
  try {
    const result = await api("/import", {
      method: "POST",
      body: {
        content: importFile.value,
        format: importFilename.value.toLowerCase().endsWith(".json")
          ? "json"
          : "csv",
        car_id: importCar.value ? Number(importCar.value) : null,
      },
    });
    modal.value = null;
    await refresh(true);
    notify(
      `Imported ${result.new_tickets} tickets. Updated ${result.updated_tickets}.`,
    );
  } catch (error) {
    formError.value = error.message;
  } finally {
    saving.value = false;
  }
}
function onEscape(event) {
  if (event.key === "Escape") {
    mobileMenu.value = false;
    modal.value = null;
    detailTicket.value = null;
    selectedStreet.value = "";
  }
}
function visible() {
  if (document.visibilityState !== "hidden") {
    if (followNow.value) jumpNow();
    refresh();
  }
}
watch([day, hour, historyDays], () => {
  loadActivity();
});
watch(
  [() => form.value.plate, () => form.value.plate_state],
  ([value, state], [previous, previousState]) => {
    if (
      normalizePlate(value) !== normalizePlate(previous) ||
      state !== previousState
    ) {
      lookupRequest++;
      lookupBusy.value = false;
      lookup.value = null;
      confirmNoTickets.value = false;
      formError.value = "";
    }
  },
);
watch(
  form,
  () => {
    if (modal.value === "car" && !editing.value) {
      try {
        sessionStorage.setItem(draftKey, JSON.stringify(form.value));
      } catch {}
    }
  },
  { deep: true },
);
watch(modal, (value) => {
  if (value !== "car") {
    try {
      sessionStorage.removeItem(draftKey);
    } catch {}
    lookupRequest++;
    lookupBusy.value = false;
    scanPreview.value = "";
  }
});
onMounted(async () => {
  try {
    const draft = JSON.parse(sessionStorage.getItem(draftKey) || "null");
    if (
      draft &&
      (draft.name || draft.plate || draft.email || draft.plate_state)
    ) {
      openCar();
      form.value = {
        name: draft.name || "",
        plate: draft.plate || "",
        email: draft.email || "",
        plate_state: draft.plate_state || "",
      };
    }
  } catch {}
  await refresh(true);
  if (disposed) return;
  interval = setInterval(() => {
    if (document.visibilityState === "hidden") return;
    if (followNow.value) {
      const current = localNow();
      day.value = current.day;
      hour.value = current.hour;
    }
    refresh();
  }, 5000);
  document.addEventListener("keydown", onEscape);
  document.addEventListener("visibilitychange", visible);
  window.addEventListener("hashchange", hashChanged);
});
onBeforeUnmount(() => {
  disposed = true;
  activityRequest++;
  clearInterval(interval);
  clearTimeout(toastTimer);
  document.removeEventListener("keydown", onEscape);
  document.removeEventListener("visibilitychange", visible);
  window.removeEventListener("hashchange", hashChanged);
});
</script>

<template>
  <div
    class="app-layout"
    :class="{ 'map-page': page === 'map', 'tickets-page': page === 'tickets' }"
  >
    <ShareLinks v-if="sharingOpen" @close="sharingOpen = false" />
    <aside class="sidebar">
      <a
        class="brand"
        :href="phone ? '#today' : '#map'"
        @click.prevent="navigate(phone ? 'today' : 'map')"
        ><span class="brand-mark">P<span></span></span
        ><span>curbwatch<span class="brand-period">.</span></span></a
      >
      <div class="workspace-label">YOUR WORKSPACE</div>
      <nav aria-label="Main navigation">
        <button
          :class="{ active: page === 'today' }"
          @click="navigate('today')"
        >
          <House :size="19" />Today
        </button>
        <button :class="{ active: page === 'map' }" @click="navigate('map')">
          <MapIcon :size="19" />Street activity<ChevronRight
            v-if="page === 'map'"
            :size="15"
            class="nav-arrow"
          />
        </button>
        <button :class="{ active: page === 'cars' }" @click="navigate('cars')">
          <CarFront :size="19" />Vehicles<span class="nav-count">{{
            cars.length
          }}</span>
        </button>
        <button
          :class="{ active: page === 'tickets' }"
          @click="navigate('tickets')"
        >
          <ReceiptText :size="19" />Ticket history<span class="nav-count">{{
            stats.tickets || 0
          }}</span>
        </button>
        <button
          :class="{ active: page === 'settings' }"
          @click="navigate('settings')"
        >
          <SettingsIcon :size="19" />Settings
        </button>
      </nav>
      <button
        class="mobile-menu-button"
        aria-label="Open account and app menu"
        aria-haspopup="dialog"
        :aria-expanded="mobileMenu"
        @click="mobileMenu = true"
      >
        <Ellipsis :size="24" />
      </button>
      <button
        class="sidebar-scan"
        aria-label="Scan a plate"
        @click="scannerOpen = true"
      >
        <ScanLine :size="17" /><span>Scan a plate</span>
      </button>
      <button class="sidebar-add" @click="openCar()">
        <Plus :size="17" />Add a vehicle
      </button>
      <div class="sidebar-bottom">
        <div class="monitor-card">
          <span class="eyebrow">KEEPING AN EYE OUT</span>
          <div class="monitor-icon"><Route :size="28" /></div>
          <strong>A clearer view of<br />your everyday streets.</strong>
          <p>Built from your cars.<br />Informed by your history.</p>
          <button @click="modal = 'help'">
            How it works <ArrowUpRight :size="15" />
          </button>
        </div>
        <div class="sidebar-account">
          <div>
            <strong>{{ user.name || user.email }}</strong><small>{{
              user.role === "admin" ? "Administrator" : "Member"
            }}</small>
          </div>
          <button
            aria-label="Sign out"
            title="Sign out"
            @click="emit('logout')"
          >
            <LogOut :size="18" />
          </button>
        </div>
      </div>
    </aside>

    <main>
      <header class="topbar">
        <div class="breadcrumb">
          Workspace <ChevronRight :size="13" /><span>{{ title }}</span>
        </div>
        <div class="topbar-right">
          <PwaControls /> <MapPin :size="14" />{{ runtime.locationLabel
          }}<span class="topbar-divider"></span
          ><span class="sync-status"
            ><i
              :class="{
                online:
                  stats.hourly_checks_running && online && !showingSnapshot,
              }"
            ></i
            >{{
              showingSnapshot || !online
                ? "Saved view"
                : stats.hourly_checks_running
                  ? "Scheduled checks on"
                  : "Checker offline"
            }}</span
          >
        </div>
      </header>
      <div class="page-content">
        <div
          v-if="!online || showingSnapshot"
          class="offline-banner"
          role="status"
        >
          <WifiOff :size="17" /><span
            >{{
              showingSnapshot
                ? `Saved view from ${dateTime(snapshotAt)}. `
                : "You’re offline. "
            }}Connect to refresh tickets, check a new plate, or save
            changes.</span
          >
        </div>
        <div v-if="connectionError && online" class="error-banner">
          <CircleAlert :size="18" />{{ connectionError
          }}<button @click="refresh(true)">Retry</button>
        </div>
        <div
          class="page-heading"
          :class="{ 'today-heading': page === 'today' }"
        >
          <div>
            <div class="eyebrow">
              {{
                page === "today"
                  ? "A LITTLE LOCAL KNOWLEDGE"
                  : page === "map"
                    ? "A LITTLE LOCAL KNOWLEDGE"
                    : page === "cars"
                      ? "YOUR PARKING, TOGETHER"
                      : page === "settings"
                        ? "YOUR WORKSPACE, YOUR PEOPLE"
                        : "EVERY TICKET, ONE PLACE"
              }}
            </div>
            <h1>{{ title }}<span class="heading-dot">.</span></h1>
            <p>
              {{
                page === "today"
                  ? "A quick look at your street and your garage."
                  : page === "map"
                    ? "Explore the patterns behind your parking tickets."
                    : page === "cars"
                      ? "Cars for you and your friends. Data plates for a fuller street history."
                      : page === "settings"
                        ? "Manage your account and who can access your garage."
                        : "The full picture, from the first ticket to the latest update."
              }}
            </p>
          </div>
          <div
            v-if="!['settings', 'today'].includes(page)"
            class="heading-actions"
          >
            <button
              v-if="page === 'map' && user.role === 'admin'"
              class="button secondary"
              @click="sharingOpen = true"
            >
              <Share2 :size="17" /><span>Share map</span>
            </button>
            <button class="button secondary" @click="scannerOpen = true">
              <ScanLine :size="17" /><span>Scan plate</span>
            </button>
            <button
              class="button secondary"
              :disabled="!online"
              @click="quickPlateOpen = true"
            >
              <Plus :size="17" />Quick add plate
            </button>
            <button
              v-if="page === 'tickets'"
              class="button secondary"
              @click="openImport"
            >
              <Upload :size="16" />Import history</button
            ><button
              v-if="page === 'cars'"
              class="button primary"
              @click="openCar()"
            >
              <Plus :size="17" />Add car</button
            ><button
              v-else
              class="button primary"
              :disabled="checking"
              @click="checkTickets()"
            >
              <RefreshCw :size="16" :class="{ spin: checking }" />{{
                checking ? "Checking plates…" : "Check now"
              }}
            </button>
          </div>
        </div>

        <TodayDashboard
          v-if="page === 'today'"
          :vehicles="vehicleCount"
          :tickets="stats.tickets || 0"
          :checking="checking"
          :version="activityVersion"
          @navigate="navigate"
          @street="viewNearbyStreet"
          @scan="scannerOpen = true"
          @check="checkTickets()"
          @plate="quickPlateOpen = true"
          @car="openCar()"
        />

        <Settings
          v-if="page === 'settings'"
          :user="user"
          @session="emit('session', $event)"
          @logout="emit('logout')"
        />
        <div v-if="busyRun" class="check-banner">
          <LoaderCircle :size="17" class="spin" /><span>{{
            busyRun.status === "queued"
              ? "Your ticket check is queued."
              : `Checking your plates · ${busyRun.completed_cars} of ${busyRun.total_cars} vehicles complete`
          }}</span
          ><span>Updates appear automatically</span>
        </div>

        <div v-if="page === 'map'" class="stats-row">
          <button class="stat-card" @click="navigate('cars')">
            <span class="stat-icon"><CarFront :size="19" /></span>
            <div>
              <span>Plates monitored</span
              ><strong
                >{{ cars.length
                }}<small>{{ activeCount }} monitoring</small></strong
              >
            </div>
            <ArrowUpRight :size="16" class="stat-arrow" />
          </button>
          <button class="stat-card" @click="navigate('tickets')">
            <span class="stat-icon"><ReceiptText :size="19" /></span>
            <div>
              <span>Tickets recorded</span
              ><strong
                >{{ stats.tickets || 0
                }}<small>Across your history</small></strong
              >
            </div>
            <ArrowUpRight :size="16" class="stat-arrow" />
          </button>
          <div class="stat-card">
            <span class="stat-icon"><Route :size="19" /></span>
            <div>
              <span>Streets in your history</span
              ><strong
                >{{ stats.streets || 0
                }}<small>{{ runtime.locationLabel }}</small></strong
              >
            </div>
            <span class="stat-tag">YOUR DATA</span>
          </div>
        </div>

        <template v-if="page === 'map'">
          <div
            v-if="activity && !activity.period.ticket_count && stats.tickets"
            class="history-empty-note"
          >
            No verified tickets in this period. Choose a longer period or All
            history to include older tickets.
          </div>
          <div class="map-workspace">
            <section class="map-panel">
              <div class="map-toolbar">
                <div class="segmented">
                  <button class="selected">
                    <MapIcon :size="15" />Street map</button
                  ><button @click="navigate('tickets')">
                    <ReceiptText :size="15" />Ticket list
                  </button>
                </div>
                <HistoryPeriod
                  v-model="historyDays"
                  :period="activity?.period"
                />
              </div>
              <StreetMap
                ref="mapRef"
                :activity="activity"
                :selected="selectedStreet"
                @select="selectedStreet = $event"
              />
              <div class="timeline-panel">
                <div class="timeline-heading">
                  <div>
                    <span class="eyebrow">EXPLORE BY HOUR</span
                    ><strong
                      >{{ hourRange
                      }}<small>{{ runtime.timezoneLabel }}</small></strong
                    >
                  </div>
                  <div class="timeline-date">
                    <button aria-label="Previous day" @click="moveDay(-1)">
                      <ChevronLeft :size="15" /></button
                    ><label class="date-picker"
                      ><CalendarDays :size="15" /><span>{{
                        selectedDayLabel
                      }}</span
                      ><input
                        v-model="day"
                        type="date"
                        aria-label="Activity date"
                        @change="followNow = false" /></label
                    ><button aria-label="Next day" @click="moveDay(1)">
                      <ChevronRight :size="15" /></button
                    ><button
                      class="now-button"
                      :class="{ following: followNow }"
                      @click="jumpNow"
                    >
                      <span></span>Now
                    </button>
                  </div>
                </div>
                <TimelinePlayback
                  :playing="playing"
                  :speed="speed"
                  :disabled="
                    !activity ||
                    showingSnapshot ||
                    !online ||
                    Boolean(connectionError)
                  "
                  @toggle="togglePlayback"
                  @speed="setSpeed"
                />
                <div
                  class="hour-chart"
                  role="group"
                  aria-label="Choose an hour"
                >
                  <button
                    v-for="h in 24"
                    :key="h"
                    :class="{ chosen: hour === h - 1 }"
                    :aria-label="`${hourLabel(h - 1)}, ${activity?.hourly_counts?.[h - 1] || 0} tickets in the selected period`"
                    :title="`${activity?.hourly_counts?.[h - 1] || 0} tickets in the selected period. Every ticket counts equally.`"
                    :aria-pressed="hour === h - 1"
                    @click="selectHour(h - 1)"
                  >
                    <span
                      class="hour-bar"
                      :style="{
                        height: `${6 + ((activity?.hourly_counts?.[h - 1] || 0) / hourlyMax) * 34}px`,
                      }"
                    ></span
                    ><span class="hour-label">{{
                      (h - 1) % 3 === 0 || hour === h - 1
                        ? hourLabel(h - 1)
                        : "·"
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
                    >Bars show ticket counts in the selected period. No age
                    weighting.</span
                  ><span>12am — 11pm</span>
                </div>
              </div>
            </section>

            <div
              v-if="streetSheetOpen"
              class="street-sheet-backdrop"
              @click="selectedStreet = ''"
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
              <template v-if="selectedSummary"
                ><div class="street-panel-heading">
                  <button class="text-button" @click="selectedStreet = ''">
                    <X v-if="phone" :size="18" /><ChevronLeft
                      v-else
                      :size="15"
                    />{{
                      phone ? "Close street details" : "All streets"
                    }}</button
                  ><span class="level-badge" :class="selectedSummary.level">{{
                    selectedSummary.level === "insufficient"
                      ? "Limited data"
                      : selectedSummary.level
                  }}</span>
                </div>
                <div class="street-detail">
                  <span class="eyebrow">STREET OVERVIEW</span>
                  <h2>{{ selectedSummary.name }}</h2>
                  <p>Activity at {{ hourLabel(hour) }}</p>
                  <div class="evidence-box">
                    <strong>{{ selectedSummary.sample_tickets }}</strong><span
                      >exact-hour
                      {{
                        selectedSummary.sample_tickets === 1
                          ? "ticket"
                          : "tickets"
                      }}
                      in this period, across<br />{{
                        selectedSummary.distinct_days
                      }}
                      {{
                        selectedSummary.distinct_days === 1 ? "day" : "days"
                      }}</span
                    >
                  </div>
                  <dl>
                    <div>
                      <dt>Tickets in period</dt>
                      <dd>{{ selectedSummary.period_tickets }}</dd>
                    </div>
                    <div>
                      <dt>Ticketed days at this hour</dt>
                      <dd>
                        {{ selectedSummary.distinct_days }} /
                        {{ selectedSummary.observed_days }}
                      </dd>
                    </div>
                    <div>
                      <dt>Tickets / observed day</dt>
                      <dd>
                        {{ selectedSummary.tickets_per_observed_day ?? "—" }}
                      </dd>
                    </div>
                    <div>
                      <dt>Latest ticket</dt>
                      <dd>{{ shortDate(selectedSummary.last_ticket_at) }}</dd>
                    </div>
                    <div>
                      <dt>Location precision</dt>
                      <dd>
                        {{
                          selectedSummary.mapped
                            ? "Street level"
                            : "Unmapped place"
                        }}
                      </dd>
                    </div>
                  </dl>
                  <p class="detail-note">
                    {{ selectedSummary.basis }}.
                    {{
                      selectedSummary.score === null
                        ? "Fewer than three exact-hour tickets across two dates; shown as limited data."
                        : "Color reflects the share of this street’s ticketed days with a ticket at this hour."
                    }}
                  </p>
                  <button
                    class="button secondary full"
                    @click="showStreetTickets(selectedSummary.street_key)"
                  >
                    View street’s tickets<ArrowRight :size="15" />
                  </button></div
              ></template>
              <template v-else
                ><div class="street-panel-heading">
                  <div>
                    <h2>
                      Your streets<span>{{
                        activity?.streets?.length || 0
                      }}</span>
                    </h2>
                    <p>Activity around {{ hourLabel(hour) }}</p>
                  </div>
                  <button
                    class="icon-button"
                    aria-label="How activity is estimated"
                    @click="modal = 'help'"
                  >
                    <CircleHelp :size="17" />
                  </button>
                </div>
                <div class="street-search">
                  <Search :size="15" /><input
                    v-model="streetSearch"
                    placeholder="Find a street"
                    aria-label="Find a street"
                  />
                </div>
                <div class="street-list">
                  <button
                    v-for="street in streetList"
                    :key="street.street_key"
                    class="street-row"
                    @click="selectedStreet = street.street_key"
                  >
                    <span
                      class="street-row-icon"
                      :class="
                        street.score === null && street.sample_tickets > 0
                          ? 'observed'
                          : street.level
                      "
                      ><Route :size="16" /></span
                    ><span class="street-row-info"
                      ><strong>{{ street.name }}</strong
                      ><span>{{
                        street.mapped
                          ? `${street.period_tickets} ${street.period_tickets === 1 ? "ticket" : "tickets"} in this period`
                          : "Location not matched to a street"
                      }}</span
                      ><span
                        v-if="
                          street.score === null && street.sample_tickets > 0
                        "
                        class="observed-tag"
                        >Observed · limited data</span
                      ></span
                    ><span class="activity-indicator" :class="street.level"
                      ><i></i><i></i><i></i></span
                    ><ChevronRight :size="14" />
                  </button>
                  <div v-if="!streetList.length" class="small-empty">
                    <Route :size="27" /><strong>{{
                      streetSearch
                        ? "No matching streets"
                        : "Your history starts here"
                    }}</strong>
                    <p>
                      {{
                        streetSearch
                          ? "Try another street name."
                          : "Run your first check to discover the streets in your ticket history."
                      }}
                    </p>
                    <button
                      v-if="!streetSearch"
                      class="text-button"
                      :disabled="checking"
                      @click="checkTickets()"
                    >
                      Check plates <ArrowRight :size="14" />
                    </button>
                  </div></div
              ></template>
              <div class="street-panel-footer">
                <CircleHelp :size="16" />
                <p>
                  Based on your monitored plates.<br /><strong
                    >Limited data doesn’t mean no enforcement.</strong
                  >
                </p>
              </div>
            </aside>
          </div>
          <p
            v-if="activity?.unverified_tickets || activity?.unmapped_tickets"
            class="data-note"
          >
            {{
              activity?.unverified_tickets
                ? `${activity.unverified_tickets} imported tickets await issue-time verification. `
                : ""
            }}{{
              activity?.unmapped_tickets
                ? `${activity.unmapped_tickets} ticket locations could not be matched to a street.`
                : ""
            }}
          </p>
          <div class="map-bottom-note">
            <span
              ><Clock3 :size="14" />{{
                stats.last_success_at
                  ? `Last checked ${dateTime(stats.last_success_at)}`
                  : "Ready for your first ticket check"
              }}</span
            ><button @click="modal = 'help'">
              Understanding the map <ArrowUpRight :size="13" />
            </button>
          </div>
          <div v-if="stats.tickets && !evidenceCount" class="insight-note">
            <span class="insight-symbol">i</span>
            <p>
              <strong>A small sample tells part of the story.</strong> Blue
              dashed streets have observations in this period with too little
              data for a score. Gray streets have no observations at this hour
              in this period.
            </p>
          </div>
        </template>

        <template v-if="page === 'cars'">
          <div class="section-toolbar">
            <div class="filter-pills">
              <button
                class="filter-pill"
                :class="{ selected: recordFilter === 'vehicle' }"
                :aria-pressed="recordFilter === 'vehicle'"
                @click="recordFilter = 'vehicle'"
              >
                Cars <b>{{ vehicleCount }}</b>
              </button>
              <button
                class="filter-pill"
                :class="{ selected: recordFilter === 'plate' }"
                :aria-pressed="recordFilter === 'plate'"
                @click="recordFilter = 'plate'"
              >
                Data plates <b>{{ plateCount }}</b>
              </button>
              <button
                class="filter-pill"
                :class="{ selected: !recordFilter }"
                :aria-pressed="!recordFilter"
                @click="recordFilter = ''"
              >
                All <b>{{ cars.length }}</b>
              </button>
              <span class="monitoring-summary"
                ><i></i>{{ activeCount }} monitoring</span
              >
            </div>
            <div class="search-field">
              <Search :size="17" /><input
                v-model="search"
                placeholder="Search name or plate"
                aria-label="Search vehicles"
              />
            </div>
          </div>
          <div class="vehicle-grid">
            <article
              v-for="car in filteredCars"
              :key="car.id"
              class="vehicle-card"
              :class="{ paused: !car.active }"
            >
              <div class="vehicle-card-top">
                <span class="vehicle-icon"><CarFront :size="23" /></span
                ><span class="monitoring-pill" :class="{ paused: !car.active }"
                  ><i></i>{{ car.active ? "Monitoring" : "Paused" }}</span
                ><button
                  class="icon-button"
                  :aria-label="
                    car.record_type === 'plate'
                      ? `Add car details for ${car.plate}`
                      : `Edit ${car.plate}`
                  "
                  @click="openCar(car)"
                >
                  <Pencil :size="16" />
                </button>
              </div>
              <h2>{{ car.name }}</h2>
              <p v-if="car.record_type === 'plate'" class="data-plate-label">
                Data plate · No email notifications
              </p>
              <a
                v-if="car.email"
                class="vehicle-email"
                :href="`mailto:${car.email}`"
                >{{ car.email }}</a
              >
              <div class="license-plate">
                <span>{{
                  plateStates[car.plate_state] || "PARKING CHECKER"
                }}</span><strong>{{ car.plate }}</strong
                ><span>{{
                  car.plate_state
                    ? `${car.plate_state} · ${car.record_type === "plate" ? "DATA PLATE" : "TRACKED CAR"}`
                    : "STATE NOT SET"
                }}</span>
              </div>
              <div class="vehicle-metrics">
                <div>
                  <span>Tickets recorded</span
                  ><strong>{{ car.ticket_count }}</strong>
                </div>
                <div>
                  <span>Outstanding balance</span
                  ><strong :class="{ 'has-balance': car.balance_cents > 0 }">{{
                    money(car.balance_cents)
                  }}</strong>
                </div>
                <div
                  class="spent-metric"
                  title="Recorded charges for tickets marked paid in full. The source does not itemize partial payments."
                >
                  <span>Total spent</span
                  ><strong>{{ money(car.total_spent_cents) }}</strong
                  ><small>Paid ticket totals</small>
                </div>
              </div>
              <div v-if="car.last_error" class="vehicle-error">
                <CircleAlert :size="13" />{{ car.last_error }}
              </div>
              <div class="vehicle-last-check">
                <Clock3 :size="13" />{{
                  car.last_success_at
                    ? `Checked ${dateTime(car.last_success_at)}`
                    : "Waiting for its first check"
                }}
              </div>
              <div class="vehicle-card-actions">
                <button :disabled="checking" @click="checkTickets(car.id)">
                  <RefreshCw :size="14" :class="{ spin: checking }" />Check
                  tickets</button
                ><button @click="toggleCar(car)">
                  <Pause v-if="car.active" :size="14" /><Play
                    v-else
                    :size="14"
                  />{{ car.active ? "Pause" : "Resume" }}
                </button>
              </div>
            </article>
            <button
              class="add-vehicle-card"
              @click="
                recordFilter === 'plate' ? (quickPlateOpen = true) : openCar()
              "
            >
              <span><Plus :size="27" /></span
              ><strong>{{
                recordFilter === "plate"
                  ? "Grow the street history."
                  : "One more set of wheels?"
              }}</strong>
              <p>
                {{
                  recordFilter === "plate"
                    ? "Add just a plate and state to collect ticket data."
                    : "Add a car with a name, plate and optional email."
                }}
              </p>
              <span class="add-vehicle-link"
                >{{ recordFilter === "plate" ? "Quick add plate" : "Add car"
                }}<ArrowRight :size="15"
              /></span>
            </button>
          </div>
          <div class="page-footnote">
            <Clock3 :size="14" />Active plates are checked every hour. Pausing
            keeps all existing ticket history.
          </div>
        </template>

        <template v-if="page === 'tickets'">
          <div class="ticket-summary">
            <div>
              <span>ALL RECORDED TICKETS</span
              ><strong>{{ stats.tickets || 0 }}</strong>
            </div>
            <div>
              <span>OUTSTANDING BALANCE</span
              ><strong>{{ money(stats.balance_cents) }}</strong>
            </div>
            <div>
              <span>HISTORY STARTS</span
              ><strong class="summary-date">{{
                stats.oldest_ticket
                  ? shortDate(stats.oldest_ticket)
                  : "Your first check"
              }}</strong>
            </div>
            <ReceiptText :size="57" />
          </div>
          <div class="section-toolbar">
            <div class="search-field wide">
              <Search :size="17" /><input
                v-model="search"
                placeholder="Search plate, street, or ticket number"
                aria-label="Search tickets"
              />
            </div>
            <select v-model="ticketCar" aria-label="Filter tickets by vehicle">
              <option value="">All vehicles</option>
              <option v-for="car in cars" :key="car.id" :value="car.id">
                {{ car.name }} · {{ plateLabel(car) }}
              </option></select
            ><span class="result-count"
              >{{ filteredTickets.length }} records</span
            >
          </div>
          <div
            class="ticket-table-wrap"
            :class="{ 'has-tickets': filteredTickets.length }"
          >
            <table class="ticket-table">
              <thead>
                <tr>
                  <th>Ticket / vehicle</th>
                  <th>Issue date <span>ET</span></th>
                  <th>Location & violation</th>
                  <th>Status</th>
                  <th class="align-right">Balance</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="ticket in filteredTickets"
                  :key="ticket.id"
                  tabindex="0"
                  @click="detailTicket = ticket"
                  @keydown.enter="detailTicket = ticket"
                >
                  <td>
                    <strong>#{{ ticket.ticket_number }}</strong
                    ><span class="table-plate"
                      >{{ plateLabel(ticket)
                      }}<small>{{ ticket.car_name }}</small></span
                    >
                  </td>
                  <td>
                    <strong>{{ shortDate(ticket.issued_at) }}</strong><span>{{
                      ticket.issued_at
                        ? new Intl.DateTimeFormat("en-US", {
                            timeZone: runtime.timezone,
                            hour: "numeric",
                            minute: "2-digit",
                          }).format(new Date(ticket.issued_at))
                        : "Issue time unavailable"
                    }}</span>
                  </td>
                  <td class="location-cell">
                    <strong>{{ ticket.location_name }}</strong><span>{{
                      ticket.description
                    }}</span>
                  </td>
                  <td>
                    <span
                      class="ticket-status"
                      :class="{
                        paid: ticket.status_id === 19,
                        outstanding: ticket.balance_cents > 0,
                      }"
                      >{{ ticket.status }}</span
                    >
                  </td>
                  <td class="align-right">
                    <strong>{{ money(ticket.balance_cents) }}</strong><span
                      >{{ money(ticket.fine_cents) }} fine</span
                    >
                  </td>
                  <td><ArrowUpRight :size="16" /></td>
                </tr>
              </tbody>
            </table>
            <div class="mobile-ticket-list" aria-label="Tickets">
              <button
                v-for="ticket in filteredTickets"
                :key="ticket.id"
                class="mobile-ticket-card"
                @click="detailTicket = ticket"
              >
                <span class="mobile-ticket-top"
                  ><strong>{{
                    ticket.location_name || "Location unavailable"
                  }}</strong
                  ><ArrowUpRight :size="18"
                /></span>
                <span class="mobile-ticket-description">{{
                  ticket.description
                }}</span>
                <span class="mobile-ticket-meta"
                  >{{ plateLabel(ticket) }} ·
                  {{ shortDate(ticket.issued_at) }}</span
                >
                <span class="mobile-ticket-bottom"
                  ><span
                    class="ticket-status"
                    :class="{
                      paid: ticket.status_id === 19,
                      outstanding: ticket.balance_cents > 0,
                    }"
                    >{{ ticket.status }}</span
                  ><strong>{{ money(ticket.balance_cents) }}</strong></span
                >
                <span class="mobile-ticket-number"
                  >Ticket #{{ ticket.ticket_number }}</span
                >
              </button>
            </div>
            <div v-if="!filteredTickets.length" class="table-empty">
              <ReceiptText :size="34" />
              <h2>
                {{ tickets.length ? "No matching tickets" : "A fresh start." }}
              </h2>
              <p>
                {{
                  tickets.length
                    ? "Try a different search or vehicle."
                    : "Check your tracked plates to bring in their ticket history, or import an existing export."
                }}
              </p>
              <button
                v-if="!tickets.length"
                class="button primary"
                :disabled="checking"
                @click="checkTickets()"
              >
                <RefreshCw :size="15" />Check plates
              </button>
            </div>
          </div>
          <div class="page-footnote">
            <CircleHelp :size="14" />Ticket totals include paid and dismissed
            tickets. Issue times use {{ runtime.timezoneLabel }}.
          </div>
        </template>
      </div>
    </main>

    <nav class="mobile-nav" aria-label="Phone navigation">
      <button
        :class="{ active: page === 'today' }"
        :aria-current="page === 'today' ? 'page' : undefined"
        @click="navigate('today')"
      >
        <House :size="21" /><span>Today</span>
      </button>
      <button
        :class="{ active: page === 'map' }"
        :aria-current="page === 'map' ? 'page' : undefined"
        @click="navigate('map')"
      >
        <MapIcon :size="21" /><span>Map</span>
      </button>
      <button
        :class="{ active: page === 'cars' }"
        :aria-current="page === 'cars' ? 'page' : undefined"
        @click="navigate('cars')"
      >
        <CarFront :size="21" /><span>Vehicles</span>
      </button>
      <button
        :class="{ active: page === 'tickets' }"
        :aria-current="page === 'tickets' ? 'page' : undefined"
        @click="navigate('tickets')"
      >
        <ReceiptText :size="21" /><span>Tickets</span>
      </button>
    </nav>

    <div
      v-if="mobileMenu"
      class="modal-overlay mobile-menu-overlay"
      @click.self="mobileMenu = false"
    >
      <section
        ref="menuPanel"
        class="modal mobile-app-menu"
        role="dialog"
        aria-modal="true"
        aria-labelledby="app-menu-title"
        tabindex="-1"
      >
        <button
          class="modal-close icon-button"
          aria-label="Close app menu"
          @click="mobileMenu = false"
        >
          <X :size="22" />
        </button>
        <h2 id="app-menu-title">Your workspace</h2>
        <p class="mobile-menu-account">{{ user.name || user.email }}</p>
        <button @click="navigate('settings')">
          <SettingsIcon :size="20" />Settings & account<ChevronRight
            :size="17"
          />
        </button>
        <button
          v-if="user.role === 'admin'"
          @click="
            mobileMenu = false;
            sharingOpen = true;
          "
        >
          <Share2 :size="20" />Share map<ChevronRight :size="17" />
        </button>
        <button
          @click="
            mobileMenu = false;
            openImport();
          "
        >
          <Upload :size="20" />Import history<ChevronRight :size="17" />
        </button>
        <button
          @click="
            mobileMenu = false;
            modal = 'help';
          "
        >
          <CircleHelp :size="20" />How activity works<ChevronRight :size="17" />
        </button>
        <div class="mobile-menu-install"><PwaControls /></div>
        <p class="mobile-menu-status">
          {{ runtime.locationLabel }} ·
          {{
            !online || showingSnapshot
              ? "Saved view"
              : stats.hourly_checks_running
                ? "Scheduled checks on"
                : "Checker offline"
          }}
        </p>
        <button
          @click="
            mobileMenu = false;
            emit('logout');
          "
        >
          <LogOut :size="20" />Sign out
        </button>
      </section>
    </div>

    <Transition name="toast"
      ><div
        v-if="toast"
        class="toast-message"
        :class="toast.kind"
        role="status"
      >
        <CircleCheck v-if="toast.kind === 'success'" :size="20" /><CircleAlert
          v-else
          :size="20"
        /><span>{{ toast.message }}</span
        ><button aria-label="Dismiss notification" @click="toast = null">
          <X :size="16" />
        </button></div
    ></Transition>

    <PlateScanner
      v-if="scannerOpen"
      @close="scannerOpen = false"
      @choose="chooseScannedPlate"
      @manual="enterPlateManually"
    />
    <QuickPlateForm
      v-if="quickPlateOpen"
      @close="quickPlateOpen = false"
      @saved="plateSaved"
    />
    <div v-if="modal" class="modal-overlay" @click.self="modal = null">
      <section
        class="modal"
        ref="modalPanel"
        role="dialog"
        aria-modal="true"
        :aria-label="
          modal === 'car'
            ? editing
              ? editing.record_type === 'plate'
                ? 'Add car details'
                : 'Edit car'
              : 'Add car'
            : modal === 'import'
              ? 'Import ticket history'
              : 'How activity works'
        "
      >
        <button
          class="modal-close icon-button"
          aria-label="Close dialog"
          @click="modal = null"
        >
          <X :size="20" />
        </button>
        <template v-if="modal === 'car'">
          <span class="modal-icon"><CarFront :size="26" /></span
          ><span class="eyebrow">{{
            editing ? "YOUR GROWING GARAGE" : "CARS FOR YOU AND YOUR FRIENDS"
          }}</span>
          <h2>
            {{
              editing
                ? editing.record_type === "plate"
                  ? "Add car details."
                  : "Your car, your details."
                : "Add a car."
            }}
          </h2>
          <p>
            {{
              editing
                ? editing.record_type === "plate"
                  ? "Turn this data plate into a car with a name, contact email and notifications. Its ticket history stays with it."
                  : "Update this car’s name, plate state and optional contact email."
                : "Add a name, plate and optional email for ticket notifications. Check the plate’s ticket history before saving."
            }}
          </p>
          <img
            v-if="scanPreview"
            :src="scanPreview"
            class="review-plate-photo"
            alt="Cropped plate photo to compare with the detected text"
          />
          <form @submit.prevent="saveCar">
            <label for="vehicle-name"
              >Car or owner name
              <span>{{ editing ? "" : "(optional)" }}</span></label
            >
            <input
              id="vehicle-name"
              ref="nameInput"
              v-model="form.name"
              placeholder="e.g. My daily driver"
              maxlength="80"
              :required="!!editing"
            />
            <label for="vehicle-email">Email <span>(optional)</span></label
            ><input
              id="vehicle-email"
              v-model="form.email"
              type="email"
              placeholder="name@example.com"
              maxlength="254"
              autocomplete="email"
            /><span class="field-hint"
              >Receives new-ticket alerts and monthly summaries when email is
              enabled.</span
            >
            <label for="vehicle-plate">License plate</label
            ><input
              id="vehicle-plate"
              v-model="form.plate"
              class="plate-input"
              placeholder="ABC1234"
              maxlength="18"
              :disabled="!!editing || saving"
              required
              autocomplete="off"
              autocapitalize="characters"
              spellcheck="false"
            />
            <span class="field-hint">{{
              scanPreview
                ? "Compare this with the photo. Check O/0, I/1, and B/8 carefully."
                : "Letters and numbers. Spaces and dashes are handled for you."
            }}</span>
            <label for="vehicle-plate-state"
              >Plate state <span>(optional)</span></label
            >
            <SelectMenu
              id="vehicle-plate-state"
              v-model="form.plate_state"
              label="Plate state (optional)"
              :options="plateStateOptions"
              :disabled="saving"
            />
            <span class="field-hint"
              >State is saved for reference. Syracuse ticket searches use the
              plate number without a state filter.</span
            >
            <button
              v-if="!editing"
              type="button"
              class="button secondary full lookup-button"
              :disabled="lookupBusy || saving || !online"
              @click="lookupPlate"
            >
              <LoaderCircle v-if="lookupBusy" :size="16" class="spin" /><Search
                v-else
                :size="16"
              />{{
                lookupBusy
                  ? "Checking with Syracuse…"
                  : lookup
                    ? "Check tickets again"
                    : "Check tickets before adding"
              }}
            </button>
            <div
              v-if="lookup"
              class="plate-lookup-result"
              :class="lookup.outcome"
              role="status"
            >
              <template v-if="lookup.ticket_count"
                ><CircleCheck :size="19" />
                <div>
                  <strong
                    >{{ lookup.ticket_count }}
                    {{
                      lookup.ticket_count === 1
                        ? "ticket found"
                        : "tickets found"
                    }}
                    for {{ lookup.plate }}</strong
                  ><span
                    >{{ money(lookup.balance_cents) }} outstanding. These
                    tickets will be saved with the vehicle.</span
                  >
                  <ul>
                    <li
                      v-for="ticket in lookup.tickets.slice(0, 3)"
                      :key="ticket.ticket_number"
                    >
                      {{ ticket.location_name }} ·
                      {{ shortDate(ticket.issued_at) }}
                    </li>
                  </ul>
                </div></template
              >
              <template v-else
                ><CircleAlert :size="19" />
                <div>
                  <strong>No tickets found for {{ lookup.plate }}</strong
                  ><span
                    >This can be a valid plate with no tickets. A ticket search
                    doesn’t verify a vehicle registration. Check the text before
                    saving.</span
                  >
                </div></template
              >
            </div>
            <label v-if="lookup?.outcome === 'no_tickets'" class="confirm-plate"
              ><input v-model="confirmNoTickets" type="checkbox" /><span
                >I checked the plate text and want to track it even though no
                tickets were found.</span
              ></label
            >
            <div v-if="formError" class="form-error" role="alert">
              <CircleAlert :size="16" />{{ formError }}
            </div>
            <div class="modal-actions">
              <button
                type="button"
                class="button secondary"
                @click="modal = null"
              >
                Cancel</button
              ><button
                class="button primary"
                :disabled="
                  saving ||
                  lookupBusy ||
                  !online ||
                  (!editing &&
                    (!lookup ||
                      (lookup.outcome === 'no_tickets' && !confirmNoTickets)))
                "
              >
                <LoaderCircle v-if="saving" :size="16" class="spin" /><Plus
                  v-else-if="!editing"
                  :size="16"
                /><Check v-else :size="16" />{{
                  saving
                    ? "Saving…"
                    : editing
                      ? "Save changes"
                      : "Start tracking"
                }}
              </button>
            </div>
          </form>
          <div class="modal-note">
            <Clock3 :size="15" />New plates join the monitoring schedule.
          </div>
        </template>
        <template v-else-if="modal === 'import'"
          ><span class="modal-icon"><Upload :size="25" /></span
          ><span class="eyebrow">BRING YOUR HISTORY</span>
          <h2>Pick up where you left off.</h2>
          <p>
            Import a NocoDB ticket export as CSV or JSON. Existing tickets are
            matched by ticket number.
          </p>
          <form @submit.prevent="submitImport">
            <label for="import-car">Vehicle for these tickets</label
            ><select id="import-car" v-model="importCar">
              <option value="">Detect from the License Plate column</option>
              <option v-for="car in cars" :key="car.id" :value="car.id">
                {{ car.name }} · {{ plateLabel(car) }}
              </option></select
            ><span class="field-hint"
              >Choose a vehicle if your export doesn’t include license plates.
              Export each vehicle’s tickets separately.</span
            ><label class="upload-zone"
              ><Upload :size="24" /><strong>{{
                importFilename || "Choose a CSV or JSON file"
              }}</strong
              ><span>Up to 5 MB</span
              ><input type="file" accept=".csv,.json" @change="readImport"
            /></label>
            <div v-if="formError" class="form-error" role="alert">
              <CircleAlert :size="16" />{{ formError }}
            </div>
            <div class="modal-actions">
              <button
                type="button"
                class="button secondary"
                @click="modal = null"
              >
                Cancel</button
              ><button class="button primary" :disabled="saving || !importFile">
                <Upload :size="16" />{{
                  saving ? "Importing…" : "Import tickets"
                }}
              </button>
            </div>
          </form>
          <div class="modal-note">
            Legacy timestamps stay unverified until a live check confirms them.
          </div></template
        >
        <template v-else
          ><span class="modal-icon"><Route :size="26" /></span
          ><span class="eyebrow">READING THE PATTERNS</span>
          <h2>History, with a little context.</h2>
          <p>
            The map uses tickets for your monitored cars to show historical
            enforcement activity at the selected hour.
          </p>
          <div class="help-items">
            <div>
              <span>01</span>
              <p>
                <strong>You choose the history.</strong> Three months (90 days)
                is the default. Use the history selector for one week, one
                month, six months, one year or all history. The period ends on
                the selected date. Every included ticket counts equally; no age
                weighting, adjacent-hour smoothing or weekday preference is
                applied.
              </p>
            </div>
            <div>
              <span>02</span>
              <p>
                <strong>Read the supporting counts.</strong> The index is the
                share of a street’s ticketed dates with a ticket in the exact
                selected hour. Green/amber/orange correspond to less than 25%,
                25–59%, and at least 60% of these dates. A color score needs
                three tickets across two dates at this hour. Sparse observations
                are blue dashed; gray means no exact-hour observations in the
                period.
              </p>
            </div>
            <div>
              <span>03</span>
              <p>
                <strong>Compare periods to spot changes.</strong> Switch between
                a week, three months and longer history to see which hours
                appear in each. The bars and street highlights always use the
                same period. Extending the window includes older observations
                without fading them.
              </p>
            </div>
            <div>
              <span>04</span>
              <p>
                <strong>An estimate, not a live location.</strong> These are
                historical observations, not the chance an officer is present.
                Days without tickets do not tell us whether a monitored car was
                parked there. Street names may cover multiple blocks. Ticket
                posting can be delayed.
              </p>
            </div>
          </div>
          <button class="button primary full" @click="modal = null">
            Got it<Check :size="16" /></button
        ></template>
      </section>
    </div>

    <div
      v-if="detailTicket"
      class="modal-overlay"
      @click.self="detailTicket = null"
    >
      <section
        class="modal ticket-detail-modal"
        ref="ticketPanel"
        role="dialog"
        aria-modal="true"
        aria-label="Ticket details"
      >
        <button
          class="modal-close icon-button"
          aria-label="Close ticket details"
          @click="detailTicket = null"
        >
          <X :size="20" /></button
        ><span class="modal-icon"><ReceiptText :size="25" /></span
        ><span class="eyebrow">TICKET DETAILS</span>
        <h2>#{{ detailTicket.ticket_number }}</h2>
        <p>{{ detailTicket.car_name }} · {{ detailTicket.plate }}</p>
        <div class="ticket-detail-location">
          <MapPin :size="20" />
          <div>
            <strong>{{ detailTicket.location_name }}</strong><span>{{
              dateTime(detailTicket.issued_at)
            }}</span>
          </div>
        </div>
        <p class="ticket-violation">{{ detailTicket.description }}</p>
        <dl class="ticket-detail-fields">
          <div>
            <dt>Status</dt>
            <dd>{{ detailTicket.status }}</dd>
          </div>
          <div>
            <dt>Fine</dt>
            <dd>{{ money(detailTicket.fine_cents) }}</dd>
          </div>
          <div>
            <dt>Surcharges</dt>
            <dd>{{ money(detailTicket.surcharge_cents) }}</dd>
          </div>
          <div class="balance-row">
            <dt>Outstanding balance</dt>
            <dd>{{ money(detailTicket.balance_cents) }}</dd>
          </div>
          <div>
            <dt>First recorded here</dt>
            <dd>{{ shortDate(detailTicket.first_seen_at) }}</dd>
          </div>
          <div>
            <dt>Issue time source</dt>
            <dd>
              {{
                detailTicket.time_source === "ticket_issue_date"
                  ? "Verified portal field"
                  : "Unverified / imported"
              }}
            </dd>
          </div>
        </dl>
        <button class="button primary full" @click="detailTicket = null">
          Done<Check :size="16" />
        </button>
      </section>
    </div>
  </div>
</template>
