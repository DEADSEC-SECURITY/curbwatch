import test from "node:test";
import assert from "node:assert/strict";
import { effectScope, ref } from "vue";
import { matchPosition, streetOptions } from "../src/location/matching.js";
import { useNearbyActivity } from "../src/location/current.js";

const road = (key, coordinates, type = "LineString") => ({
  type: "Feature",
  properties: { street_key: key, name: key },
  geometry: { type, coordinates },
});
const roads = {
  type: "FeatureCollection",
  features: [
    road("WAVERLY AVE", [
      [-76.136, 43.04],
      [-76.13, 43.04],
    ]),
    road("UNIVERSITY AVE", [
      [-76.13, 43.04],
      [-76.13, 43.043],
    ]),
    road("MARSHALL ST", [
      [-76.136, 43.042],
      [-76.13, 43.042],
    ]),
  ],
};
const point = { lat: 43.0401, lng: -76.134, accuracy: 10 };
const activity = (hour = 10, day = "2026-11-17") => ({
  date: day,
  hour,
  streets: [
    {
      street_key: "WAVERLY AVE",
      level: "moderate",
      score: 0.5,
      sample_tickets: 3,
      distinct_days: 2,
      observed_days: 4,
    },
  ],
});
const flush = async () => {
  for (let i = 0; i < 8; i++) await Promise.resolve();
};
const deferred = () => {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
};

test("matches the nearest line segment, not a street endpoint or the streets with tickets", () => {
  const result = matchPosition(point, roads);
  assert.equal(result.status, "matched");
  assert.equal(result.candidates[0].key, "WAVERLY AVE");
  assert.ok(
    result.candidates[0].distance > 10 && result.candidates[0].distance < 12,
  );
  assert.equal(
    matchPosition({ ...point, lat: 43.042 }, roads).candidates[0].key,
    "MARSHALL ST",
  );
});

test("requires a manual choice at an intersection and rejects poor accuracy and uncovered locations", () => {
  assert.equal(
    matchPosition({ ...point, lng: -76.13003, lat: 43.04001 }, roads).status,
    "ambiguous",
  );
  assert.equal(
    matchPosition({ ...point, accuracy: 100 }, roads).status,
    "inaccurate",
  );
  assert.equal(matchPosition({ ...point, lat: 42 }, roads).status, "outside");
  assert.equal(matchPosition(point, null).status, "no-geometry");
  for (const update of [{ lat: NaN }, { lng: 181 }, { accuracy: -1 }])
    assert.equal(
      matchPosition({ ...point, ...update }, roads).status,
      "unavailable",
    );
});

test("handles multiline streets, duplicate street segments and zero-length segments", () => {
  const geometry = {
    features: [
      road(
        "WAVERLY AVE",
        [
          [
            [-75, 42],
            [-75.1, 42],
          ],
          [
            [-76.136, 43.04],
            [-76.13, 43.04],
          ],
        ],
        "MultiLineString",
      ),
      road("WAVERLY AVE", [
        [-76.134, 43.04],
        [-76.134, 43.04],
      ]),
    ],
  };
  const result = matchPosition(point, geometry);
  assert.equal(result.status, "matched");
  assert.equal(result.candidates.length, 1);
  assert.equal(streetOptions(geometry).length, 1);
});

function fixture(t, overrides = {}) {
  const page = new EventTarget();
  page.visibilityState = "visible";
  const calls = [],
    positions = [],
    jobs = new Map(),
    saved = new Map();
  let now = { day: "2026-11-17", hour: 10 };
  const connected = ref(true);
  const scope = effectScope();
  const load = async (path) => {
    calls.push(path);
    return path === "/streets" ? roads : activity(now.hour, now.day);
  };
  const nearby = scope.run(() =>
    useNearbyActivity({
      load,
      clock: () => ({ ...now }),
      isOnline: () => connected.value,
      browserNavigator: {
        permissions: { query: async () => ({ state: "prompt" }) },
        geolocation: {
          getCurrentPosition: (success, failure, options) =>
            positions.push({ success, failure, options }),
        },
      },
      secure: true,
      pageDocument: page,
      storage: {
        getItem: (key) => saved.get(key),
        setItem: (key, value) => saved.set(key, value),
      },
      schedule: (callback) => {
        jobs.set(1, callback);
        return 1;
      },
      cancel: (id) => jobs.delete(id),
      ...overrides,
    }),
  );
  t.after(() => scope.stop());
  const locate = (index = positions.length - 1, location = point) =>
    positions[index].success({
      coords: {
        latitude: location.lat,
        longitude: location.lng,
        accuracy: location.accuracy,
      },
      timestamp: Date.now(),
    });
  return {
    nearby,
    calls,
    positions,
    locate,
    page,
    connected,
    jobs,
    saved,
    scope,
    setNow: (value) => {
      now = value;
    },
  };
}

test("first visit loads the current hour and 90-day history without prompting for location", async (t) => {
  const f = fixture(t);
  await f.nearby.start();
  await flush();
  assert.equal(f.positions.length, 0);
  assert.equal(f.nearby.locationStatus.value, "idle");
  assert.ok(
    f.calls.includes("/activity?day=2026-11-17&hour=10&history_days=90"),
  );
  f.nearby.locate();
  f.locate();
  assert.equal(f.nearby.street.value.key, "WAVERLY AVE");
  assert.equal(f.nearby.summary.value.level, "moderate");
  assert.deepEqual([...f.saved.values()], ["true"]);
  assert.deepEqual(f.positions[0].options, {
    enableHighAccuracy: true,
    timeout: 10000,
    maximumAge: 60000,
  });
});

test("existing permission and saved opt-in locate automatically", async (t) => {
  for (const usePreference of [true, false]) {
    const positions = [];
    const f = fixture(t, {
      storage: { getItem: () => String(usePreference), setItem() {} },
      browserNavigator: {
        permissions: { query: async () => ({ state: "granted" }) },
        geolocation: { getCurrentPosition: (...args) => positions.push(args) },
      },
    });
    await f.nearby.start();
    assert.equal(positions.length, 1);
  }
});

test("denial stops automatic requests; timeout and unavailable states offer a retry", async (t) => {
  const f = fixture(t);
  await f.nearby.start();
  f.nearby.locate();
  f.positions[0].failure({ code: 1 });
  assert.equal(f.nearby.locationStatus.value, "denied");
  f.page.dispatchEvent(new Event("visibilitychange"));
  assert.equal(f.positions.length, 1);
  f.nearby.locate();
  f.positions[1].failure({ code: 3 });
  assert.equal(f.nearby.locationStatus.value, "timeout");
  f.nearby.locate();
  f.positions[2].failure({ code: 2 });
  assert.equal(f.nearby.locationStatus.value, "unavailable");
});

test("manual street selection wins over a late location result and is kept on foreground", async (t) => {
  const f = fixture(t);
  await f.nearby.start();
  await flush();
  f.nearby.locate();
  f.nearby.selectStreet("MARSHALL ST");
  f.locate();
  f.page.dispatchEvent(new Event("visibilitychange"));
  assert.equal(f.nearby.street.value.key, "MARSHALL ST");
  assert.equal(f.nearby.summary.value, undefined);
  assert.equal(f.positions.length, 1);
});

test("foreground refreshes location; hidden tabs do no scheduled work and dispose removes listeners", async (t) => {
  const f = fixture(t);
  await f.nearby.start();
  await flush();
  f.nearby.locate();
  f.locate();
  f.page.visibilityState = "hidden";
  const count = f.calls.length;
  f.jobs.get(1)();
  assert.equal(f.calls.length, count);
  f.page.visibilityState = "visible";
  f.page.dispatchEvent(new Event("visibilitychange"));
  assert.equal(f.positions.length, 2);
  f.scope.stop();
  f.locate();
  assert.equal(f.nearby.locationStatus.value, "locating");
  assert.equal(f.jobs.size, 0);
  f.page.dispatchEvent(new Event("visibilitychange"));
  assert.equal(f.positions.length, 2);
});

test("hour and day rollover fetch current activity independently of map exploration", async (t) => {
  const f = fixture(t);
  await f.nearby.start();
  await flush();
  const count = f.calls.length;
  await f.nearby.refresh(false);
  assert.equal(f.calls.length, count);
  f.setNow({ day: "2026-11-18", hour: 0 });
  f.jobs.get(1)();
  await flush();
  assert.ok(f.calls.at(-1).includes("day=2026-11-18&hour=0&history_days=90"));
  assert.equal(f.nearby.data.value.hour, 0);
  assert.equal(f.calls.filter((path) => path === "/streets").length, 1);
});

test("offline data is marked stale and returns to current after reconnecting", async (t) => {
  const f = fixture(t);
  await f.nearby.start();
  await flush();
  f.connected.value = false;
  assert.equal(f.nearby.stale.value, true);
  const count = f.calls.length;
  await f.nearby.refresh();
  assert.equal(f.calls.length, count);
  f.connected.value = true;
  await f.nearby.refresh();
  assert.equal(f.nearby.stale.value, false);
});

test("older responses cannot replace a newer hour or update a disposed dashboard", async (t) => {
  const first = deferred(),
    second = deferred();
  let count = 0;
  const f = fixture(t, {
    load: (path) =>
      path === "/streets"
        ? Promise.resolve(roads)
        : ++count === 1
          ? first.promise
          : second.promise,
  });
  const oldRequest = f.nearby.refresh();
  f.setNow({ day: "2026-11-17", hour: 11 });
  const newRequest = f.nearby.refresh();
  second.resolve(activity(11));
  await newRequest;
  first.resolve(activity(10));
  await oldRequest;
  assert.equal(f.nearby.data.value.hour, 11);
  f.scope.stop();
  await f.nearby.refresh();
  assert.equal(count, 2);
});

test("failed geometry downloads can be retried, without posting coordinates", async (t) => {
  const calls = [];
  let fail = true;
  const f = fixture(t, {
    load: async (path) => {
      calls.push(path);
      if (path === "/streets" && fail) throw new Error("Streets unavailable");
      return path === "/streets" ? roads : activity();
    },
  });
  await f.nearby.refresh();
  assert.match(f.nearby.error.value, /Streets unavailable/);
  fail = false;
  await f.nearby.refresh();
  f.nearby.locate();
  f.locate();
  assert.equal(f.nearby.street.value.key, "WAVERLY AVE");
  assert.ok(calls.every((path) => !/lat|lng|43\.04|-76\.13/.test(path)));
});

test("insecure contexts, missing geolocation and blocked storage still support manual streets", async (t) => {
  for (const options of [
    { secure: false },
    { browserNavigator: {} },
    {
      storage: {
        getItem() {
          throw new Error("Storage disabled");
        },
        setItem() {
          throw new Error("Storage disabled");
        },
      },
    },
  ]) {
    const f = fixture(t, options);
    await f.nearby.start();
    await flush();
    f.nearby.selectStreet("WAVERLY AVE");
    assert.equal(f.nearby.summary.value.level, "moderate");
  }
});
