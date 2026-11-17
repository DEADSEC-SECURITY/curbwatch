import { createApp } from "vue";
import AuthRoot from "./AuthRoot.vue";
import "./auth.css";
import "./style.css";
import "./scanner.css";
import "./sharing.css";
import "./viewport.css";
import "./mobile.css";
import { registerPwa } from "./pwa";

createApp(AuthRoot).mount("#app");
registerPwa();
