import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { sharedManifest } from "../src/shared-pwa.js";

const origin = "https://maps.example.com";
test("shared installations retain the exact link with separate stable identities", async () => {
  const token = "A".repeat(43),
    other = "B".repeat(43);
  const manifest = await sharedManifest(token, origin);
  assert.equal(
    manifest.id,
    `${origin}/share/?app=${createHash("sha256").update(token).digest("hex")}`,
  );
  assert.deepEqual(await sharedManifest(token, origin), manifest);
  assert.notEqual((await sharedManifest(other, origin)).id, manifest.id);
  assert.equal(manifest.start_url, `${origin}/share/#${token}`);
  assert.equal(manifest.scope, `${origin}/share/`);
  assert.equal(manifest.display, "standalone");
  assert.ok(!manifest.id.includes(token));
  assert.ok(
    manifest.icons.every((icon) => icon.src.startsWith(`${origin}/icons/`)),
  );
  const normal = JSON.parse(
    await readFile(new URL("../public/manifest.webmanifest", import.meta.url)),
  );
  assert.equal(normal.start_url, "/");
  assert.equal(normal.id, "/");
});

test("incomplete or malformed shared links cannot set up an installation", async () => {
  for (const token of ["", "short", "!".repeat(43), "A".repeat(44)])
    assert.equal(await sharedManifest(token, origin), null);
});
