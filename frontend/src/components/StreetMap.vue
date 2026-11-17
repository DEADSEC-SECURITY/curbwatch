<script setup>
import { runtime } from "../runtime";
import { onMounted, onBeforeUnmount, watch, ref } from "vue";
import * as maplibregl from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";
import { Plus, Minus, LocateFixed, MapPin } from "@lucide/vue";
import { api } from "../api";

const props = defineProps({
  activity: Object,
  selected: String,
  streetData: Object,
  contextLabel: { type: String, default: "YOUR TICKET HISTORY" },
  emptyMessage: {
    type: String,
    default: "Check your plates to put your ticket history on the map.",
  },
});
const emit = defineEmits(["select"]);
const container = ref(null);
const mapError = ref(false);
maplibregl.setWorkerUrl(workerUrl);
let map,
  ready = false,
  observer,
  disposed = false;
const empty = { type: "FeatureCollection", features: [] };

function update() {
  if (!ready) return;
  map.getSource("activity")?.setData(props.activity || empty);
  if (map.getLayer("selected"))
    map.setFilter("selected", [
      "==",
      ["get", "street_key"],
      props.selected || "",
    ]);
}

function fit() {
  if (!ready) return;
  const features = props.activity?.features || [];
  if (!features.length) {
    map.flyTo({ center: runtime.mapCenter, zoom: runtime.mapZoom });
    return;
  }
  const bounds = new maplibregl.LngLatBounds();
  function add(coords) {
    if (typeof coords[0] === "number") bounds.extend(coords);
    else coords.forEach(add);
  }
  features.forEach((f) => add(f.geometry.coordinates));
  if (!bounds.isEmpty())
    map.fitBounds(bounds, {
      padding: {
        top: Math.min(80, container.value.clientHeight * 0.18),
        bottom: Math.min(65, container.value.clientHeight * 0.16),
        left: Math.min(60, container.value.clientWidth * 0.08),
        right: Math.min(60, container.value.clientWidth * 0.08),
      },
      maxZoom: 14.5,
      duration: 800,
    });
}

onMounted(async () => {
  const localStreets =
    props.streetData || (await api("/streets").catch(() => empty));
  let style = {
    version: 8,
    sources: {},
    layers: [
      {
        id: "background",
        type: "background",
        paint: { "background-color": "#e9ede5" },
      },
    ],
  };
  try {
    const response = await fetch(runtime.mapStyleUrl, {
      signal: AbortSignal.timeout(7000),
    });
    if (!response.ok) throw new Error("Map style unavailable");
    style = await response.json();
  } catch {
    mapError.value = true;
  }
  if (disposed) return;
  map = new maplibregl.Map({
    container: container.value,
    center: runtime.mapCenter,
    zoom: runtime.mapZoom,
    style,
    attributionControl: { compact: true },
    minZoom: 10,
    maxZoom: 18,
  });
  map.on("load", () => {
    map.addSource("streets", {
      type: "geojson",
      data: localStreets,
      attribution: `Street geometry: ${runtime.streetsAttribution}`,
    });
    map.addLayer({
      id: "local-roads",
      type: "line",
      source: "streets",
      paint: { "line-color": "#b7c0b2", "line-width": 1, "line-opacity": 0.28 },
    });
    map.addSource("activity", { type: "geojson", data: empty });
    const colors = [
      "match",
      ["get", "level"],
      "high",
      "#d5794f",
      "moderate",
      "#c9a749",
      "low",
      "#62958b",
      "#87949f",
    ];
    map.addLayer({
      id: "activity-casing",
      type: "line",
      source: "activity",
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": "#ffffff",
        "line-width": 10,
        "line-opacity": 0.85,
      },
    });
    map.addLayer({
      id: "activity-lines",
      type: "line",
      source: "activity",
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": colors, "line-width": 5, "line-opacity": 0.95 },
    });
    map.addLayer({
      id: "activity-observations",
      type: "line",
      source: "activity",
      filter: [
        "all",
        ["==", ["get", "level"], "insufficient"],
        [">", ["get", "sample_tickets"], 0],
      ],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": "#718db8",
        "line-width": 5,
        "line-dasharray": [1.5, 1.5],
      },
    });
    map.addLayer(
      {
        id: "selected",
        type: "line",
        source: "activity",
        filter: ["==", ["get", "street_key"], ""],
        layout: { "line-cap": "round" },
        paint: { "line-color": "#203d31", "line-width": 10 },
      },
      "activity-lines",
    );
    map.addLayer({
      id: "activity-hit",
      type: "line",
      source: "activity",
      paint: { "line-width": 24, "line-opacity": 0 },
    });
    map.on("click", "activity-hit", (e) =>
      emit("select", e.features[0].properties.street_key),
    );
    map.on("mouseenter", "activity-hit", () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", "activity-hit", () => {
      map.getCanvas().style.cursor = "";
    });
    ready = true;
    update();
    fit();
  });
  map.on("error", (e) => {
    if (e.sourceId === "basemap") mapError.value = true;
  });
  observer = new ResizeObserver(() => map?.resize());
  observer.observe(container.value);
});

watch(() => props.activity, update);
watch(
  () => props.selected,
  () => {
    update();
    const features = props.activity?.features?.filter(
      (f) => f.properties.street_key === props.selected,
    );
    if (ready && features?.length) {
      const coords = features[0].geometry.coordinates;
      const first = typeof coords[0][0] === "number" ? coords[0] : coords[0][0];
      map.easeTo({ center: first, duration: 600 });
    }
  },
);
onBeforeUnmount(() => {
  disposed = true;
  observer?.disconnect();
  map?.remove();
  ready = false;
});
defineExpose({ fit });
</script>

<template>
  <div class="map-shell">
    <div
      ref="container"
      class="map-canvas"
      :aria-label="`${runtime.locationLabel} street activity map`"
    ></div>
    <div class="map-location">
      <MapPin :size="15" /><span>Syracuse, New York</span
      ><span class="map-location-tag">{{ contextLabel }}</span>
    </div>
    <div class="map-controls">
      <button aria-label="Zoom in" @click="map?.zoomIn()">
        <Plus :size="18" />
      </button>
      <button aria-label="Zoom out" @click="map?.zoomOut()">
        <Minus :size="18" />
      </button>
      <button
        aria-label="Fit tracked streets"
        title="Fit tracked streets"
        @click="fit"
      >
        <LocateFixed :size="18" />
      </button>
    </div>
    <div v-if="!activity?.streets?.length" class="map-empty">
      <MapPin :size="21" /><strong>Your streets will appear here</strong
      ><span>{{ emptyMessage }}</span>
    </div>
    <div v-if="mapError" class="map-network-note">
      Showing local street geometry. Background tiles are unavailable.
    </div>
    <div class="map-legend">
      <span class="legend-title">ACTIVITY</span
      ><span><i class="dot low"></i>Low</span
      ><span><i class="dot moderate"></i>Moderate</span
      ><span><i class="dot high"></i>High</span
      ><span title="Tickets in this period, too few for a score"
        ><i class="dot observed"></i>Observed · limited</span
      >
      <span><i class="dot insufficient"></i>No exact-hour sample</span>
    </div>
    <div class="map-scale-note">Street locations are approximate</div>
  </div>
</template>
