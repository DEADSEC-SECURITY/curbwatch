// Match against every covered street, including streets with no ticket history.
// Coordinates stay in memory; activity is only precise to the whole street.
const METRES_PER_DEGREE = 111_195;
export const MAX_ACCURACY = 60;
export const MAX_STREET_DISTANCE = 75;

function segmentDistance(point, start, end) {
  const longitudeScale =
    METRES_PER_DEGREE * Math.cos((point.lat * Math.PI) / 180);
  const x = (start[0] - point.lng) * longitudeScale;
  const y = (start[1] - point.lat) * METRES_PER_DEGREE;
  const dx = (end[0] - start[0]) * longitudeScale;
  const dy = (end[1] - start[1]) * METRES_PER_DEGREE;
  const length = dx * dx + dy * dy;
  const along = length
    ? Math.max(0, Math.min(1, -(x * dx + y * dy) / length))
    : 0;
  return Math.hypot(x + along * dx, y + along * dy);
}

export function streetOptions(roads) {
  const streets = new Map();
  for (const feature of roads?.features || []) {
    const { street_key: key, name } = feature.properties || {};
    if (key && name) streets.set(key, { key, name });
  }
  return [...streets.values()].sort((a, b) => a.name.localeCompare(b.name));
}

export function matchPosition(point, roads) {
  if (
    !point ||
    ![point.lat, point.lng, point.accuracy].every(Number.isFinite) ||
    Math.abs(point.lat) > 90 ||
    Math.abs(point.lng) > 180 ||
    point.accuracy < 0
  )
    return { status: "unavailable", candidates: [] };
  if (point.accuracy > MAX_ACCURACY)
    return { status: "inaccurate", candidates: [] };
  if (!roads?.features?.length)
    return { status: "no-geometry", candidates: [] };

  const distances = new Map();
  for (const feature of roads.features) {
    const { street_key: key, name } = feature.properties || {};
    if (!key || !name) continue;
    const geometry = feature.geometry;
    const lines =
      geometry?.type === "LineString"
        ? [geometry.coordinates]
        : geometry?.type === "MultiLineString"
          ? geometry.coordinates
          : [];
    for (const line of lines) {
      for (let i = 1; i < line.length; i++) {
        const distance = segmentDistance(point, line[i - 1], line[i]);
        if (
          distance <= MAX_STREET_DISTANCE &&
          (!distances.has(key) || distance < distances.get(key).distance)
        )
          distances.set(key, { key, name, distance });
      }
    }
  }
  const candidates = [...distances.values()].sort(
    (a, b) => a.distance - b.distance,
  );
  if (!candidates.length) return { status: "outside", candidates };
  const ambiguous =
    candidates.length > 1 &&
    candidates[1].distance - candidates[0].distance <=
      Math.max(12, point.accuracy / 2);
  return { status: ambiguous ? "ambiguous" : "matched", candidates };
}
