import { ref, computed, onScopeDispose } from "vue";
import { matchPosition, streetOptions } from "./matching.js";

const PREFERENCE = "curbwatch-location-enabled";

export function useNearbyActivity({
  load,
  clock,
  isOnline = () => true,
  browserNavigator = typeof navigator === "undefined" ? null : navigator,
  secure = typeof window !== "undefined" && window.isSecureContext,
  pageDocument = typeof document === "undefined" ? null : document,
  storage,
  schedule = setInterval,
  cancel = clearInterval,
  clearOnError = false,
}) {
  const roads = ref(null),
    data = ref(null),
    position = ref(null);
  const locationStatus = ref("idle"),
    manualStreet = ref("");
  const loading = ref(false),
    error = ref(""),
    updatedAt = ref(null);
  const positionAt = ref(null),
    current = ref(clock());
  let disposed = false,
    started = false,
    request = 0,
    locationRequest = 0;
  let timer,
    geometryRequest,
    autoLocate = false;
  const options = computed(() => streetOptions(roads.value));
  const match = computed(() => matchPosition(position.value, roads.value));
  const street = computed(() =>
    manualStreet.value
      ? options.value.find((option) => option.key === manualStreet.value)
      : locationStatus.value === "ready" && match.value.status === "matched"
        ? match.value.candidates[0]
        : null,
  );
  const summary = computed(() =>
    data.value?.streets?.find((item) => item.street_key === street.value?.key),
  );
  const stale = computed(() =>
    Boolean(
      data.value &&
      (error.value ||
        !isOnline() ||
        data.value.date !== current.value.day ||
        data.value.hour !== current.value.hour),
    ),
  );

  function preference(value) {
    try {
      const deviceStorage =
        storage === undefined && typeof window !== "undefined"
          ? window.localStorage
          : storage;
      if (value === undefined)
        return deviceStorage?.getItem(PREFERENCE) === "true";
      deviceStorage?.setItem(PREFERENCE, String(value));
    } catch {
      /* Location also works with browser storage disabled. */
    }
    return false;
  }
  async function refresh(force = true) {
    if (disposed) return;
    current.value = clock();
    if (
      !force &&
      data.value?.date === current.value.day &&
      data.value?.hour === current.value.hour &&
      !error.value
    )
      return;
    const id = ++request;
    if (!isOnline()) {
      error.value = "Connect to load current street activity.";
      loading.value = false;
      return;
    }
    loading.value = true;
    const params = new URLSearchParams({
      day: current.value.day,
      hour: String(current.value.hour),
      history_days: "90",
    });
    try {
      geometryRequest ||= load("/streets").catch((failure) => {
        geometryRequest = null;
        throw failure;
      });
      const [activity, geometry] = await Promise.all([
        load(`/activity?${params}`),
        geometryRequest,
      ]);
      if (disposed || id !== request) return;
      data.value = activity;
      roads.value = geometry;
      updatedAt.value = new Date();
      error.value = "";
    } catch (failure) {
      if (!disposed && id === request) {
        error.value = failure.message || "Street activity could not be loaded.";
        if (clearOnError) {
          data.value = roads.value = null;
          geometryRequest = null;
        }
      }
    } finally {
      if (!disposed && id === request) loading.value = false;
    }
  }
  function locate() {
    if (disposed) return;
    if (!secure) {
      locationStatus.value = "insecure";
      return;
    }
    if (!browserNavigator?.geolocation) {
      locationStatus.value = "unsupported";
      return;
    }
    const id = ++locationRequest;
    locationStatus.value = "locating";
    manualStreet.value = "";
    const failed = (failure) => {
      if (disposed || id !== locationRequest) return;
      locationStatus.value =
        failure.code === 1
          ? "denied"
          : failure.code === 3
            ? "timeout"
            : "unavailable";
      if (failure.code === 1) {
        autoLocate = false;
        preference(false);
      }
    };
    try {
      browserNavigator.geolocation.getCurrentPosition(
        (result) => {
          if (disposed || id !== locationRequest) return;
          position.value = {
            lat: result.coords.latitude,
            lng: result.coords.longitude,
            accuracy: result.coords.accuracy,
          };
          positionAt.value = new Date(result.timestamp || Date.now());
          locationStatus.value = "ready";
          autoLocate = true;
          preference(true);
        },
        failed,
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
      );
    } catch (failure) {
      failed({ code: failure.name === "SecurityError" ? 1 : 2 });
    }
  }
  function selectStreet(key) {
    // An outstanding GPS response must not override a deliberate selection.
    locationRequest++;
    manualStreet.value = key;
    if (locationStatus.value === "locating") locationStatus.value = "idle";
  }
  function visible() {
    if (pageDocument?.visibilityState === "hidden") return;
    refresh();
    if (autoLocate && !manualStreet.value) locate();
  }
  async function start() {
    if (started || disposed) return;
    started = true;
    refresh();
    timer = schedule(() => {
      if (pageDocument?.visibilityState !== "hidden") refresh(false);
    }, 60000);
    pageDocument?.addEventListener("visibilitychange", visible);
    if (!secure || !browserNavigator?.geolocation) {
      locationStatus.value = secure ? "unsupported" : "insecure";
      return;
    }
    if (preference()) {
      autoLocate = true;
      locate();
      return;
    }
    try {
      const permission = await browserNavigator?.permissions?.query({
        name: "geolocation",
      });
      if (!disposed && locationStatus.value === "idle" && !manualStreet.value) {
        if (permission?.state === "granted") locate();
        else if (permission?.state === "denied")
          locationStatus.value = "denied";
      }
    } catch {
      /* Browsers without permission queries use the Enable location button. */
    }
  }
  onScopeDispose(() => {
    disposed = true;
    request++;
    locationRequest++;
    cancel(timer);
    pageDocument?.removeEventListener("visibilitychange", visible);
  });
  return {
    data,
    roads,
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
    start,
    refresh,
    locate,
    selectStreet,
  };
}
