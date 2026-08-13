import React from "react";
import ReactDOM from "react-dom/client";
import { Provider as ReduxProvider } from "react-redux";
import "@fontsource/manrope/400.css";
import "@fontsource/manrope/500.css";
import "@fontsource/manrope/600.css";
import "@fontsource/manrope/700.css";
import "@fontsource/dm-mono/400.css";
import "@fontsource/dm-mono/500.css";
import "@fontsource/fraunces/600.css";
import "@fontsource/fraunces/700.css";
import "@/index.css";
import App from "@/App";
import { store } from "@/store";
import AppearanceController from "@/components/theme/AppearanceController";
import { installChunkLoadRecovery } from "@/lib/chunkRecovery";

installChunkLoadRecovery();

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <ReduxProvider store={store}>
      <AppearanceController />
      <App />
    </ReduxProvider>
  </React.StrictMode>,
);
