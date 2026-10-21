/**
 * Application entry point.
 *
 * Imports i18n configuration before React renders so translations are
 * available synchronously on first render.
 */
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./i18n";
import "./index.css";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error(
    "Root element #root not found. Ensure index.html contains <div id='root'></div>.",
  );
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

