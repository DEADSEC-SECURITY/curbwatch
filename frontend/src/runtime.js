// Public deployment settings are loaded before Vue. No secrets belong in this object.
export const runtime = Object.freeze({
  timezone: "America/New_York",
  timezoneLabel: "Eastern time",
  locationLabel: "Syracuse, New York",
  mapStyleUrl: "https://tiles.openfreemap.org/styles/positron",
  mapCenter: [-76.135, 43.039],
  mapZoom: 13.5,
  streetsAttribution: "City of Syracuse",
  defaultHistoryDays: 90,
  checkIntervalSeconds: 3600,
  ...(window.CURBWATCH_CONFIG || {}),
});
