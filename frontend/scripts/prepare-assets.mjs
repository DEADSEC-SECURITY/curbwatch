import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import {
  mkdir,
  readdir,
  copyFile,
  readFile,
  writeFile,
} from "node:fs/promises";
import sharp from "sharp";

const require = createRequire(import.meta.url);
const root = resolve(import.meta.dirname, "..");
await copyFile(
  join(root, "../backend/resources/plate-states.json"),
  join(root, "src/plate-states.json"),
);
const tesseract = dirname(require.resolve("tesseract.js/package.json"));
const core = dirname(require.resolve("tesseract.js-core/package.json"));
const language = dirname(
  require.resolve("@tesseract.js-data/eng/package.json"),
);
const version = `${JSON.parse(await readFile(join(tesseract, "package.json"))).version}-${JSON.parse(await readFile(join(core, "package.json"))).version}-eng-best-int`;
const publicPath = `/ocr/${version}`;
const destination = join(root, "public", publicPath);
await mkdir(join(destination, "core"), { recursive: true });
await mkdir(join(destination, "lang"), { recursive: true });
await copyFile(
  join(tesseract, "dist/worker.min.js"),
  join(destination, "worker.min.js"),
);
for (const file of await readdir(core)) {
  if (/\.wasm(?:\.js)?$/.test(file))
    await copyFile(join(core, file), join(destination, "core", file));
}
await copyFile(
  join(language, "4.0.0_best_int/eng.traineddata.gz"),
  join(destination, "lang/eng.traineddata.gz"),
);
await writeFile(
  join(root, "src/ocr-assets.json"),
  JSON.stringify({ base: publicPath }),
);
const icon = Buffer.from(
  `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 40 40"><rect width="40" height="40" fill="#182a22"/><rect x="7" y="6" width="26" height="28" rx="7" fill="#deedb2"/><path d="M16 28V12h7a5 5 0 0 1 0 10h-7m0-5h7" fill="none" stroke="#182a22" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
);
await mkdir(join(root, "public/icons"), { recursive: true });
for (const size of [180, 192, 512])
  await sharp(icon)
    .resize(size, size)
    .png()
    .toFile(join(root, `public/icons/icon-${size}.png`));
console.log(`Prepared local OCR assets (${version}) and PWA icons.`);

// Preserve upstream notices when JS/OCR assets are distributed in the built app.
const licenses = join(root, "public/licenses");
await mkdir(licenses, { recursive: true });
for (const name of [
  "vue",
  "maplibre-gl",
  "@lucide/vue",
  "tesseract.js",
  "tesseract.js-core",
  "@tesseract.js-data/eng",
]) {
  const folder = dirname(require.resolve(`${name}/package.json`));
  for (const file of await readdir(folder)) {
    if (/^(license|copying|notice)(\.|$)/i.test(file))
      await copyFile(
        join(folder, file),
        join(licenses, `${name.replaceAll("/", "-")}-${file}`),
      );
  }
}
