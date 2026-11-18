// Keep the launch secret in the installing browser. A local manifest avoids
// putting bearer tokens in HTTP URLs, access logs, cookies or server storage.
export async function sharedManifest(
  token,
  origin,
  cryptoProvider = globalThis.crypto,
) {
  if (!/^[A-Za-z0-9_-]{43}$/.test(token)) return null;
  const digest = await cryptoProvider.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(token),
  );
  const identity = Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  const absolute = (path) => new URL(path, origin).href;
  return {
    // Fragments are stripped from app ids, so use a non-secret digest instead.
    id: absolute(`/share/?app=${identity}`),
    name: "Curbwatch Shared Map",
    short_name: "Shared map",
    description: "Current-street activity and a shared historical parking map.",
    start_url: absolute(`/share/#${token}`),
    scope: absolute("/share/"),
    display: "standalone",
    background_color: "#f6f7f4",
    theme_color: "#182a22",
    icons: [192, 512].map((size) => ({
      src: absolute(`/icons/icon-${size}.png`),
      sizes: `${size}x${size}`,
      type: "image/png",
    })),
  };
}

let manifestUrl;
export async function configureSharedManifest() {
  const token = window.location.hash.slice(1);
  const link = document.getElementById("shared-manifest");
  link?.removeAttribute("href");
  if (manifestUrl) URL.revokeObjectURL(manifestUrl);
  manifestUrl = null;
  try {
    const manifest = await sharedManifest(token, window.location.origin);
    if (manifest && window.location.hash.slice(1) === token) {
      manifestUrl = URL.createObjectURL(
        new Blob([JSON.stringify(manifest)], {
          type: "application/manifest+json",
        }),
      );
      link?.setAttribute("href", manifestUrl);
    }
  } catch {
    // Older/insecure browsers can still save the full link as a home-screen shortcut.
  }
}
