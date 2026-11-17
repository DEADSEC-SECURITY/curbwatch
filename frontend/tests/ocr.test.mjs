import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import sharp from "sharp";
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
    const svg = Buffer.from(
      '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="300"><rect width="1200" height="300" fill="white"/><text x="600" y="208" text-anchor="middle" font-size="160" font-weight="bold" font-family="DejaVu Sans, sans-serif" letter-spacing="9">DEMO6808</text></svg>',
    );
    const image = await sharp(svg).png().toBuffer();
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
