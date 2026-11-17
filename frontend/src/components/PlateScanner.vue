<script setup>
import { ref, nextTick, onBeforeUnmount, onMounted, watch } from "vue";
import {
  Camera,
  Video,
  Upload,
  X,
  ScanLine,
  LoaderCircle,
  Square,
  ArrowRight,
  CircleAlert,
  ZoomIn,
  Keyboard,
  ImagePlus,
} from "@lucide/vue";
import { createPlateReader } from "../scanner/reader";
import { DetectionTracker } from "../scanner/candidates";
import {
  stopMediaStream,
  CameraSession,
  frameRectangle,
  cameraError,
} from "../scanner/camera";

const emit = defineEmits(["close", "choose", "manual"]);
const video = ref(null),
  viewport = ref(null),
  crop = ref(null),
  photoInput = ref(null),
  uploadInput = ref(null);
const mode = ref("choose"),
  busy = ref(false),
  opening = ref(false),
  streaming = ref(false),
  scanning = ref(false);
const message = ref(""),
  error = ref(""),
  results = ref([]),
  photoLoaded = ref(false),
  zoom = ref(1);
let stream,
  image,
  imageUrl,
  alive = true,
  requestId = 0,
  scanId = 0,
  timer,
  dragging;
let offset = { x: 0, y: 0 };
const tracker = new DetectionTracker();
const cameraSession = new CameraSession();
const reader = createPlateReader((event) => {
  if (event.status === "recognizing text")
    message.value = `Reading plate… ${Math.round((event.progress || 0) * 100)}%`;
  else message.value = "Preparing the on-device reader…";
});

function stopCamera() {
  requestId++;
  scanId++;
  scanning.value = false;
  streaming.value = false;
  clearTimeout(timer);
  cameraSession.stop();
  stream = null;
  if (video.value) video.value.srcObject = null;
}
async function openCamera() {
  stopCamera();
  tracker.reset();
  mode.value = "live";
  error.value = "";
  opening.value = true;
  results.value = [];
  const id = ++requestId;
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    opening.value = false;
    error.value =
      "Live camera access needs HTTPS or localhost. For now, take or upload a photo instead.";
    return;
  }
  try {
    const requested = await cameraSession.open(() =>
      navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
      }),
    );
    if (!requested) return;
    if (!alive || id !== requestId) {
      stopMediaStream(requested);
      return;
    }
    stream = requested;
    await nextTick();
    video.value.srcObject = stream;
    await video.value.play();
    if (!alive || id !== requestId) {
      stopCamera();
      return;
    }
    streaming.value = true;
    toggleScan();
  } catch (cause) {
    if (alive && id === requestId) {
      stopCamera();
      error.value = cameraError(cause);
    }
  } finally {
    if (alive) opening.value = false;
  }
}
function capture() {
  const camera = video.value,
    view = viewport.value;
  if (!camera || !view) return null;
  const bounds = frameRectangle(
    camera.videoWidth,
    camera.videoHeight,
    view.clientWidth,
    view.clientHeight,
  );
  if (!bounds) return null;
  const canvas = document.createElement("canvas");
  canvas.width = 1200;
  canvas.height = Math.max(
    200,
    Math.round((1200 * bounds.height) / bounds.width),
  );
  canvas
    .getContext("2d")
    .drawImage(
      camera,
      bounds.x,
      bounds.y,
      bounds.width,
      bounds.height,
      0,
      0,
      canvas.width,
      canvas.height,
    );
  return canvas;
}
async function readPhoto() {
  if (!photoLoaded.value || busy.value) return;
  busy.value = true;
  error.value = "";
  results.value = [];
  try {
    const candidates = await reader.read(crop.value);
    if (!alive) return;
    const thumbnail = crop.value.toDataURL("image/jpeg", 0.8);
    results.value = candidates.map((candidate) => ({
      ...candidate,
      thumbnail,
    }));
    if (!results.value.length)
      error.value =
        "No clear plate text was found. Drag or zoom the photo to frame the number, then try again. You can also enter it manually.";
  } catch {
    if (alive)
      error.value =
        "The reader could not finish. Try a clearer photo, or enter the plate manually.";
  } finally {
    if (alive) {
      busy.value = false;
      message.value = "";
    }
  }
}
async function readFrame(id) {
  if (!alive || !scanning.value || id !== scanId) return;
  const canvas = capture();
  if (!canvas) {
    timer = setTimeout(() => readFrame(id), 500);
    return;
  }
  busy.value = true;
  try {
    const candidates = await reader.read(canvas);
    if (!alive || id !== scanId) return;
    results.value = tracker.observe(
      candidates,
      canvas.toDataURL("image/jpeg", 0.75),
    );
  } catch {
    if (alive && id === scanId) {
      scanning.value = false;
      error.value = "Live reading stopped. Try taking a photo instead.";
    }
  } finally {
    if (alive) {
      busy.value = false;
      message.value = "";
    }
    if (alive && scanning.value && id === scanId)
      timer = setTimeout(() => readFrame(id), 1000);
  }
}
function toggleScan() {
  if (scanning.value) {
    scanning.value = false;
    scanId++;
    clearTimeout(timer);
    return;
  }
  error.value = "";
  scanning.value = true;
  readFrame(++scanId);
}
async function cameraPhoto() {
  const canvas = capture();
  if (!canvas) return;
  const source = canvas.toDataURL("image/jpeg", 0.95);
  stopCamera();
  await loadPhoto(source, false);
}
function drawPhoto() {
  if (!image || !crop.value) return;
  const canvas = crop.value,
    context = canvas.getContext("2d");
  const scale =
    Math.max(canvas.width / image.width, canvas.height / image.height) *
    zoom.value;
  const width = image.width * scale,
    height = image.height * scale;
  offset.x = Math.max(
    -(width - canvas.width) / 2,
    Math.min((width - canvas.width) / 2, offset.x),
  );
  offset.y = Math.max(
    -(height - canvas.height) / 2,
    Math.min((height - canvas.height) / 2, offset.y),
  );
  context.fillStyle = "#fff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(
    image,
    (canvas.width - width) / 2 + offset.x,
    (canvas.height - height) / 2 + offset.y,
    width,
    height,
  );
}
async function loadPhoto(source, objectUrl = true) {
  stopCamera();
  mode.value = "photo";
  error.value = "";
  results.value = [];
  photoLoaded.value = false;
  if (imageUrl) URL.revokeObjectURL(imageUrl);
  imageUrl = objectUrl ? source : null;
  const loaded = new Image();
  loaded.onload = async () => {
    if (!alive) return;
    image = loaded;
    zoom.value = 1;
    offset = { x: 0, y: 0 };
    photoLoaded.value = true;
    await nextTick();
    drawPhoto();
  };
  loaded.onerror = () => {
    if (alive)
      error.value = "This image could not be opened. Try a JPEG or PNG photo.";
  };
  loaded.src = source;
}
function choosePhoto(event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    error.value = "Choose an image file.";
    return;
  }
  if (file.size > 20_000_000) {
    error.value = "Please choose a photo smaller than 20 MB.";
    return;
  }
  loadPhoto(URL.createObjectURL(file));
}
function pointerDown(event) {
  if (busy.value) return;
  crop.value.setPointerCapture(event.pointerId);
  dragging = {
    x: event.clientX,
    y: event.clientY,
    left: offset.x,
    top: offset.y,
  };
}
function pointerMove(event) {
  if (!dragging || busy.value) return;
  const ratio = crop.value.width / crop.value.clientWidth;
  offset.x = dragging.left + (event.clientX - dragging.x) * ratio;
  offset.y = dragging.top + (event.clientY - dragging.y) * ratio;
  drawPhoto();
  results.value = [];
}
function choose(candidate) {
  stopCamera();
  emit("choose", {
    plate: candidate.plate,
    thumbnail: candidate.thumbnail,
    method: mode.value,
  });
}
function close() {
  stopCamera();
  emit("close");
}
function visibility() {
  if (document.hidden) {
    stopCamera();
    opening.value = false;
    message.value = "";
  }
}
function escape(event) {
  if (event.key === "Escape") close();
}
watch(zoom, () => {
  drawPhoto();
  results.value = [];
});
onMounted(() => {
  document.addEventListener("visibilitychange", visibility);
  document.addEventListener("keydown", escape);
});
onBeforeUnmount(() => {
  alive = false;
  stopCamera();
  reader.close();
  if (imageUrl) URL.revokeObjectURL(imageUrl);
  document.removeEventListener("visibilitychange", visibility);
  document.removeEventListener("keydown", escape);
});
</script>

<template>
  <div class="modal-overlay scanner-overlay" @click.self="close">
    <section
      class="modal scanner-modal"
      role="dialog"
      aria-modal="true"
      aria-label="Scan a license plate"
    >
      <button
        class="modal-close icon-button"
        aria-label="Close scanner"
        @click="close"
      >
        <X :size="21" />
      </button>
      <span class="modal-icon"><ScanLine :size="27" /></span
      ><span class="eyebrow">FROM THE CURB TO YOUR GARAGE</span>
      <h2>Point. Read. Review.</h2>
      <p>
        Read a plate from a photo or your live camera. You’ll confirm the text
        and check for tickets before adding it.
      </p>
      <input
        ref="photoInput"
        class="hidden-file"
        type="file"
        accept="image/*"
        capture="environment"
        aria-label="Take a plate photo"
        @change="choosePhoto"
      />
      <input
        ref="uploadInput"
        class="hidden-file"
        type="file"
        accept="image/*"
        aria-label="Upload a plate photo"
        @change="choosePhoto"
      />
      <div class="scanner-choices">
        <button
          class="button"
          :class="mode === 'photo' ? 'primary' : 'secondary'"
          :disabled="busy"
          @click="photoInput.click()"
        >
          <Camera :size="17" />Take photo</button
        ><button
          class="button secondary"
          :disabled="busy"
          @click="uploadInput.click()"
        >
          <Upload :size="16" />Upload photo</button
        ><button
          class="button"
          :class="mode === 'live' ? 'primary' : 'secondary'"
          :disabled="opening || busy"
          @click="openCamera"
        >
          <Video :size="17" />{{ opening ? "Opening…" : "Live camera" }}
        </button>
      </div>
      <div v-if="mode === 'choose'" class="scanner-intro">
        <div class="plate-demo">ABC 1234</div>
        <strong>Give the number a clear frame.</strong
        ><span>Good light, a straight angle, and a close view work best.</span>
      </div>
      <template v-if="mode === 'live'">
        <div ref="viewport" class="camera-viewport">
          <video ref="video" autoplay playsinline muted></video>
          <div class="scan-guide">
            <i></i><span>Keep the plate number inside this frame</span>
          </div>
          <div v-if="opening" class="camera-opening">
            <LoaderCircle class="spin" :size="27" /><span
              >Waiting for camera permission…</span
            >
          </div>
          <span v-if="scanning" class="live-scanning"
            ><i></i>Reading live frames</span
          >
        </div>
        <div class="camera-actions">
          <button
            v-if="streaming"
            class="button primary"
            :disabled="busy && !scanning"
            @click="toggleScan"
          >
            <Square v-if="scanning" :size="15" /><ScanLine
              v-else
              :size="17"
            />{{ scanning ? "Stop scanning" : "Start scanning" }}</button
          ><button
            v-if="streaming && !scanning"
            class="button secondary"
            :disabled="busy"
            @click="cameraPhoto"
          >
            <Camera :size="16" />Read this frame</button
          ><button
            v-if="!streaming && !opening"
            class="button secondary"
            @click="openCamera"
          >
            <Video :size="16" />Open camera
          </button>
        </div>
        <p class="scanner-hint">
          Live scanning waits for the same text in two frames. Video isn’t
          saved. Stop or close the scanner to turn off the camera.
        </p>
      </template>
      <template v-if="mode === 'photo'">
        <div class="photo-crop">
          <canvas
            ref="crop"
            width="1200"
            height="300"
            aria-label="Plate photo crop; drag to position the plate number"
            @pointerdown="pointerDown"
            @pointermove="pointerMove"
            @pointerup="dragging = null"
            @pointercancel="dragging = null"
          ></canvas>
          <div v-if="!photoLoaded" class="crop-loading">
            <ImagePlus :size="25" /><span>Loading photo…</span>
          </div>
        </div>
        <div v-if="photoLoaded" class="photo-controls">
          <label
            ><ZoomIn :size="16" /><span>Zoom</span
            ><input
              v-model.number="zoom"
              type="range"
              min="1"
              max="5"
              step=".1"
              aria-label="Photo zoom"
              :disabled="busy" /></label
          ><button class="button primary" :disabled="busy" @click="readPhoto">
            <LoaderCircle v-if="busy" class="spin" :size="16" /><ScanLine
              v-else
              :size="17"
            />{{ busy ? "Reading…" : "Read plate" }}
          </button>
        </div>
        <p class="scanner-hint">
          Drag the photo and adjust the zoom so only the plate number fills the
          frame. Photos stay on your device.
        </p>
      </template>
      <div v-if="busy" class="scanner-progress" role="status">
        <LoaderCircle :size="16" class="spin" />{{
          message || "Reading on your device…"
        }}
      </div>
      <div v-if="error" class="form-error" role="alert">
        <CircleAlert :size="17" />{{ error }}
      </div>
      <div v-if="results.length" class="scan-results">
        <span class="eyebrow">{{
          mode === "live" ? "SEEN IN MULTIPLE FRAMES" : "POSSIBLE PLATE TEXT"
        }}</span><button
          v-for="candidate in results"
          :key="candidate.plate"
          @click="choose(candidate)"
        >
          <strong>{{ candidate.plate }}</strong><span
            >Review & check tickets</span
          ><ArrowRight :size="18" />
        </button>
        <p>
          Check every character. O/0, I/1, and B/8 can look alike; recognition
          doesn’t validate a registration.
        </p>
      </div>
      <button
        class="scanner-manual text-button"
        @click="
          stopCamera();
          emit('manual');
        "
      >
        <Keyboard :size="16" />Enter a plate manually<ArrowRight :size="14" />
      </button>
    </section>
  </div>
</template>
