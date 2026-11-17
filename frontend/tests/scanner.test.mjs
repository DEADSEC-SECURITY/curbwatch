import test from "node:test";
import assert from "node:assert/strict";
import {
  plateCandidates,
  DetectionTracker,
  normalizePlate,
} from "../src/scanner/candidates.js";
import {
  frameRectangle,
  stopMediaStream,
  cameraError,
  CameraSession,
} from "../src/scanner/camera.js";

test("a camera permission request resolving after close cannot leave the camera active", async () => {
  const camera = new CameraSession();
  let resolvePermission,
    stopped = 0;
  const pending = camera.open(
    () =>
      new Promise((resolve) => {
        resolvePermission = resolve;
      }),
  );
  camera.stop();
  resolvePermission({ getTracks: () => [{ stop: () => stopped++ }] });
  assert.equal(await pending, null);
  assert.equal(stopped, 1);
  await camera.open(async () => ({
    getTracks: () => [{ stop: () => stopped++ }],
  }));
  camera.stop();
  assert.equal(stopped, 2);
});

test("OCR candidates keep vanity plates, drop labels, and never guess O/0", () => {
  const result = plateCandidates({
    text: "NEW YORK\nDEMO68O8\nVANITY\n",
    confidence: 90,
  });
  assert(result.some((c) => c.plate === "DEMO68O8"));
  assert(!result.some((c) => c.plate === "DEMO6808"));
  assert(result.some((c) => c.plate === "VANITY"));
  assert(!result.some((c) => c.plate === "NEWYORK"));
  assert.equal(normalizePlate(" demo-6808 "), "DEMO6808");
});
test("live detection requires matching readings, without merging ambiguous characters", () => {
  const tracker = new DetectionTracker();
  const first = [{ plate: "DEMO68O8", confidence: 90 }],
    second = [{ plate: "DEMO6808", confidence: 90 }];
  assert.equal(tracker.observe(first, "photo", 1000).length, 0);
  assert.equal(tracker.observe(second, "photo", 2000).length, 0);
  assert.equal(tracker.observe(second, "photo", 3000)[0].plate, "DEMO6808");
});
test("weak and widely separated detections do not become stable plates", () => {
  const tracker = new DetectionTracker();
  assert.equal(
    tracker.observe([{ plate: "ABC1234", confidence: 20 }], "", 1).length,
    0,
  );
  tracker.observe([{ plate: "ABC1234", confidence: 90 }], "", 1000);
  assert.equal(
    tracker.observe([{ plate: "ABC1234", confidence: 90 }], "", 20000).length,
    0,
  );
});
test("camera frame crop accounts for object-fit cover and stays inside the source", () => {
  for (const [sw, sh, vw, vh] of [
    [1920, 1080, 400, 300],
    [1080, 1920, 400, 300],
    [1280, 720, 320, 240],
  ]) {
    const crop = frameRectangle(sw, sh, vw, vh);
    assert(crop.x >= 0 && crop.y >= 0 && crop.width > 0 && crop.height > 0);
    assert(crop.x + crop.width <= sw && crop.y + crop.height <= sh);
  }
  assert.equal(frameRectangle(0, 0, 320, 240), null);
});
test("closing the camera stops every owned track, including late streams", () => {
  let stopped = 0;
  stopMediaStream({
    getTracks: () => [{ stop: () => stopped++ }, { stop: () => stopped++ }],
  });
  stopMediaStream(null);
  assert.equal(stopped, 2);
  assert(cameraError({ name: "NotAllowedError" }).includes("declined"));
});
