import test from "node:test";
import assert from "node:assert/strict";
import { ref, effectScope } from "vue";
import { useTimelinePlayback } from "../src/timeline/playback.js";

function fixture(t, initialHour = 17, pageDocument = null) {
  let elapsed = 0,
    nextId = 0;
  const jobs = new Map();
  const clock = {
    schedule(callback, delay) {
      const id = ++nextId;
      jobs.set(id, { at: elapsed + delay, callback });
      return id;
    },
    cancel(id) {
      jobs.delete(id);
    },
    tick(milliseconds) {
      const target = elapsed + milliseconds;
      while (true) {
        const next = [...jobs].sort((a, b) => a[1].at - b[1].at)[0];
        if (!next || next[1].at > target) break;
        elapsed = next[1].at;
        jobs.delete(next[0]);
        next[1].callback();
      }
      elapsed = target;
    },
  };
  const hour = ref(initialHour),
    following = ref(true),
    available = ref(true),
    busy = ref(false);
  const scope = effectScope();
  const player = scope.run(() =>
    useTimelinePlayback({
      hour,
      following,
      available: () => available.value,
      busy: () => busy.value,
      schedule: clock.schedule,
      cancel: clock.cancel,
      pageDocument,
    }),
  );
  t.after(() => scope.stop());
  return { hour, following, available, busy, clock, jobs, scope, ...player };
}

test("play shows each hour for two seconds by default and stops following the wall clock", (t) => {
  const player = fixture(t);
  player.toggle();
  assert.equal(player.playing.value, true);
  assert.equal(player.following.value, false);
  player.clock.tick(1999);
  assert.equal(player.hour.value, 17);
  player.clock.tick(1);
  assert.equal(player.hour.value, 18);
  player.clock.tick(2000);
  assert.equal(player.hour.value, 19);
});

test("the 24-hour loop wraps from 11pm to midnight and returns to its starting hour", (t) => {
  const player = fixture(t, 23);
  player.toggle();
  player.clock.tick(2000);
  assert.equal(player.hour.value, 0);
  player.clock.tick(23 * 2000);
  assert.equal(player.hour.value, 23);
  assert.equal(player.jobs.size, 1);
});

test("changing speed restarts the wait without leaving a second timer", (t) => {
  const player = fixture(t, 5);
  player.toggle();
  player.clock.tick(500);
  player.setSpeed(1000);
  assert.equal(player.jobs.size, 1);
  player.clock.tick(999);
  assert.equal(player.hour.value, 5);
  player.clock.tick(1);
  assert.equal(player.hour.value, 6);
  player.setSpeed(2000);
  player.clock.tick(1999);
  assert.equal(player.hour.value, 6);
  player.clock.tick(1);
  assert.equal(player.hour.value, 7);
});

test("pause keeps the selected hour, and resume continues from that hour", (t) => {
  const player = fixture(t);
  player.toggle();
  player.clock.tick(2000);
  player.pause();
  player.clock.tick(10000);
  assert.equal(player.hour.value, 18);
  assert.equal(player.jobs.size, 0);
  player.hour.value = 10;
  player.toggle();
  player.clock.tick(2000);
  assert.equal(player.hour.value, 11);
});

test("a slow request holds the hour instead of skipping views or catching up in a burst", (t) => {
  const player = fixture(t);
  player.busy.value = true;
  player.toggle();
  player.clock.tick(10000);
  assert.equal(player.hour.value, 17);
  assert.equal(player.jobs.size, 1);
  player.busy.value = false;
  player.clock.tick(2000);
  assert.equal(player.hour.value, 18);
});

test("losing access or leaving the map cancels playback immediately", (t) => {
  const player = fixture(t);
  player.toggle();
  player.available.value = false;
  assert.equal(player.playing.value, false);
  assert.equal(player.jobs.size, 0);
  player.clock.tick(10000);
  assert.equal(player.hour.value, 17);
  player.toggle();
  assert.equal(player.playing.value, false);
});

test("hiding the app pauses it, and returning does not restart it unexpectedly", (t) => {
  class Page extends EventTarget {
    visibilityState = "visible";
  }
  const page = new Page();
  const player = fixture(t, 17, page);
  player.toggle();
  page.visibilityState = "hidden";
  page.dispatchEvent(new Event("visibilitychange"));
  assert.equal(player.playing.value, false);
  assert.equal(player.jobs.size, 0);
  player.toggle();
  assert.equal(player.playing.value, false);
  page.visibilityState = "visible";
  page.dispatchEvent(new Event("visibilitychange"));
  player.clock.tick(10000);
  assert.equal(player.hour.value, 17);
});

test("disposing a view stops its timer so it cannot keep advancing in the background", (t) => {
  const player = fixture(t);
  player.toggle();
  player.scope.stop();
  assert.equal(player.jobs.size, 0);
  player.clock.tick(10000);
  assert.equal(player.hour.value, 17);
});
