# Third-party components and data

The Curbwatch license applies to this project's original code. It does not relicense its dependencies or public datasets.

| Component | Upstream license / source |
|---|---|
| Vue | MIT — https://github.com/vuejs/core |
| MapLibre GL JS | BSD-3-Clause — https://github.com/maplibre/maplibre-gl-js |
| Lucide Vue | ISC — https://github.com/lucide-icons/lucide |
| Tesseract.js and its WASM core | Apache-2.0 — https://github.com/naptha/tesseract.js and https://github.com/naptha/tesseract.js-core |
| Bundled English OCR data package | MIT package terms — https://github.com/naptha/tessdata; underlying Tesseract trained data has its upstream terms |
| FastAPI, HTTPX, Uvicorn and Python runtime dependencies | Their respective installed distribution licenses; pinned in requirements.lock.txt |
| Authlib | BSD-3-Clause — https://github.com/authlib/authlib |
| Celery | BSD-3-Clause — https://github.com/celery/celery |

Frontend builds copy upstream license notices into `/licenses/` alongside generated OCR assets. Python packages keep their installed license metadata in the container. Package manifests/lockfiles identify the full dependency set.

## Map data

Background styles/tiles come from OpenFreeMap, OpenMapTiles and OpenStreetMap under their own terms. In-map attribution is retained. See https://openfreemap.org/ and https://www.openstreetmap.org/copyright.

Street geometry is downloaded separately from the configured source (default: City of Syracuse road inventory). No municipal dataset is included in this repository or covered by Curbwatch's software license. The downloader records source and attribution in the runtime GeoJSON cache. Dataset users should consult the original publisher's terms. Tests contain a tiny synthetic geometry fixture, not the municipal road dataset.
