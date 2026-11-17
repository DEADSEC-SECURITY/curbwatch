import assets from "../ocr-assets.json";
import { plateCandidates } from "./candidates";

export function createPlateReader(progress = () => {}) {
  let workerPromise,
    closed = false;
  async function worker() {
    if (closed) throw new Error("Scanner closed");
    if (!workerPromise) {
      workerPromise = import("tesseract.js")
        .then(async ({ createWorker }) => {
          const result = await createWorker("eng", 1, {
            workerPath: `${assets.base}/worker.min.js`,
            corePath: `${assets.base}/core`,
            langPath: `${assets.base}/lang`,
            logger: (message) => {
              if (!closed) progress(message);
            },
          });
          if (closed) {
            await result.terminate();
            throw new Error("Scanner closed");
          }
          await result.setParameters({
            tessedit_char_whitelist: "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ",
            tessedit_pageseg_mode: "7",
            user_defined_dpi: "300",
            preserve_interword_spaces: "1",
          });
          return result;
        })
        .catch((error) => {
          workerPromise = undefined;
          throw error;
        });
    }
    return workerPromise;
  }
  return {
    async read(canvas) {
      const engine = await worker();
      if (closed) return [];
      const prepared = document.createElement("canvas");
      prepared.width = canvas.width;
      prepared.height = canvas.height;
      const context = prepared.getContext("2d", { willReadFrequently: true });
      context.drawImage(canvas, 0, 0);
      const image = context.getImageData(0, 0, prepared.width, prepared.height);
      for (let i = 0; i < image.data.length; i += 4) {
        const gray =
          image.data[i] * 0.299 +
          image.data[i + 1] * 0.587 +
          image.data[i + 2] * 0.114;
        const contrast = Math.max(0, Math.min(255, (gray - 128) * 1.5 + 128));
        image.data[i] = image.data[i + 1] = image.data[i + 2] = contrast;
      }
      context.putImageData(image, 0, 0);
      const { data } = await engine.recognize(
        prepared,
        {},
        { text: true, blocks: true },
      );
      return closed ? [] : plateCandidates(data);
    },
    async close() {
      closed = true;
      try {
        const engine = await workerPromise;
        await engine?.terminate();
      } catch {
        /* Initialization may already have failed. */
      }
    },
  };
}
