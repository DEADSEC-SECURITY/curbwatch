import { runtime } from "./runtime";
let csrfToken = "";
export function setCsrfToken(value) {
  csrfToken = value;
}
export async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
        ...options.headers,
      },
      body:
        options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new Error(
      navigator.onLine
        ? "The local app could not be reached. Make sure it is running, then try again."
        : "You’re offline. Connect before checking tickets or saving changes.",
    );
  }
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error("Unable to reach the local app. Please refresh.");
  }
  if (!response.ok) {
    const message = Array.isArray(data.detail)
      ? data.detail.map((e) => e.msg).join(". ")
      : data.detail;
    if (
      response.status === 401 &&
      !["/auth/login", "/auth/session"].includes(path)
    )
      window.dispatchEvent(new Event("curbwatch:unauthorized"));
    const failure = new Error(
      message || "Something went wrong. Please try again.",
    );
    failure.status = response.status;
    throw failure;
  }
  return data;
}

export const money = (cents) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: cents % 100 ? 2 : 0,
  }).format((cents || 0) / 100);
export const dateTime = (date) =>
  date
    ? new Intl.DateTimeFormat("en-US", {
        timeZone: runtime.timezone,
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
      }).format(new Date(date))
    : "Not checked yet";
export const shortDate = (date) =>
  date
    ? new Intl.DateTimeFormat("en-US", {
        timeZone: runtime.timezone,
        month: "short",
        day: "numeric",
        year: "numeric",
      }).format(new Date(date))
    : "Unknown date";
export const hourLabel = (hour) =>
  `${hour % 12 || 12}${hour < 12 ? "am" : "pm"}`;
export function localNow() {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: runtime.timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(new Date())
      .map((p) => [p.type, p.value]),
  );
  return {
    day: `${parts.year}-${parts.month}-${parts.day}`,
    hour: Number(parts.hour),
  };
}
