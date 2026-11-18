import { createApp } from "vue";
import SharedMap from "./SharedMap.vue";
import "./style.css";
import "./shared.css";
import "./viewport.css";
import "./mobile.css";
import { registerPwa } from "./pwa";
import { configureSharedManifest } from "./shared-pwa.js";

createApp(SharedMap).mount("#app");
configureSharedManifest();
window.addEventListener("hashchange", configureSharedManifest);
registerPwa({ workerUrl: "/share/sw.js", scope: "/share/" });
