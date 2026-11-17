import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { readFile } from "node:fs/promises";
import { createWorker } from "tesseract.js";
import { plateCandidates } from "../src/scanner/candidates.js";

test(
  "bundled on-device OCR reads a clear plate without any remote language download",
  { timeout: 60000 },
  async () => {
    const require = createRequire(import.meta.url);
    const langPath = join(
      dirname(require.resolve("@tesseract.js-data/eng/package.json")),
      "4.0.0_best_int",
    );
    // A fixed synthetic raster keeps host font substitution out of the OCR test.
    const image = await readFile(new URL("./fixtures/plate.png", import.meta.url));
    const worker = await createWorker("eng", 1, {
      langPath,
      cacheMethod: "none",
    });
    try {
      await worker.setParameters({
        tessedit_char_whitelist: "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ",
        tessedit_pageseg_mode: "7",
      });
      const { data } = await worker.recognize(
        image,
        {},
        { text: true, blocks: true },
      );
      assert(
        plateCandidates(data).some(
          (candidate) => candidate.plate === "DEMO6808",
        ),
        `Recognized: ${data.text}`,
      );
    } finally {
      await worker.terminate();
    }
  },
);
