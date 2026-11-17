const labels = new Set([
  "NEWYORK",
  "NEW",
  "YORK",
  "EXCELSIOR",
  "PARKING",
  "CHECKER",
  "LICENSE",
  "VEHICLE",
  "STATE",
  "PLATE",
  "PASSENGER",
  "REGISTRATION",
  "AMERICA",
  "UNITED",
  "STATES",
]);

export function normalizePlate(text) {
  return String(text || "")
    .toUpperCase()
    .replace(/[\s-]/g, "");
}

export function plateCandidates(data) {
  const lines = (data.blocks || []).flatMap((block) =>
    (block.paragraphs || []).flatMap((paragraph) => paragraph.lines || []),
  );
  const sources = lines.length
    ? lines
    : String(data.text || "")
        .split(/\r?\n/)
        .map((text) => ({ text, confidence: data.confidence || 0 }));
  const found = new Map();
  for (const line of sources) {
    const words = String(line.text || "")
      .toUpperCase()
      .replace(/[^A-Z0-9 -]/g, " ")
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    for (const value of [words.join(""), ...words]) {
      const plate = normalizePlate(value);
      if (!/^[A-Z0-9]{3,10}$/.test(plate) || labels.has(plate)) continue;
      if (/^[A-Z]+$/.test(plate) && plate.length < 4) continue;
      const confidence = Math.max(
        0,
        Math.min(100, Number(line.confidence ?? data.confidence ?? 0)),
      );
      if (confidence < 25) continue;
      if (!found.has(plate) || confidence > found.get(plate).confidence) {
        found.set(plate, {
          plate,
          confidence,
          lookalikes: /[O0I1B8S5Z2]/.test(plate),
        });
      }
    }
  }
  const rank = (item) =>
    item.confidence +
    (/[A-Z]/.test(item.plate) && /\d/.test(item.plate) ? 12 : 0) +
    (item.plate.length >= 5 && item.plate.length <= 8 ? 8 : 0);
  return [...found.values()].sort((a, b) => rank(b) - rank(a)).slice(0, 6);
}

export class DetectionTracker {
  constructor() {
    this.entries = new Map();
  }
  reset() {
    this.entries.clear();
  }
  observe(candidates, thumbnail, timestamp = Date.now()) {
    for (const candidate of candidates.filter(
      (item) => item.confidence >= 45,
    )) {
      const previous = this.entries.get(candidate.plate);
      const recent = previous && timestamp - previous.lastSeen < 12000;
      this.entries.set(candidate.plate, {
        ...candidate,
        hits: recent ? previous.hits + 1 : 1,
        lastSeen: timestamp,
        thumbnail,
      });
    }
    for (const [key, item] of this.entries)
      if (timestamp - item.lastSeen > 45000) this.entries.delete(key);
    if (this.entries.size > 36) {
      const oldest = [...this.entries.values()].sort(
        (a, b) => a.lastSeen - b.lastSeen,
      );
      for (const item of oldest.slice(0, this.entries.size - 36))
        this.entries.delete(item.plate);
    }
    return [...this.entries.values()]
      .filter((item) => item.hits >= 2)
      .sort((a, b) => b.lastSeen - a.lastSeen)
      .slice(0, 12);
  }
}
