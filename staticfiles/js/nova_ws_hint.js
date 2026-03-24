/**
 * Sets the visible WebSocket URL hint on the dashboard (`#nova-ws-url-hint`).
 *
 * Uses `data-nova-ws-url` on `#nova-voice-form` when set; otherwise same-host `wss`/`ws` + path.
 *
 * Example:
 *   Loaded with defer after dashboard HTML; runs on DOMContentLoaded or immediately.
 */
(function () {
  "use strict";

  /**
   * Compute mic WebSocket URL for display (matches NovaStreamClient defaults).
   * @returns {string}
   */
  function computeWsUrl() {
    var form = document.getElementById("nova-voice-form");
    var custom = form && form.getAttribute("data-nova-ws-url");
    if (custom && (custom.indexOf("ws:") === 0 || custom.indexOf("wss:") === 0)) {
      return custom;
    }
    var path = (form && form.getAttribute("data-nova-ws-path")) || "/ws/audio/nova";
    var proto = window.location.protocol === "https:" ? "wss" : "ws";
    return proto + "://" + window.location.host + path;
  }

  function update() {
    var el = document.getElementById("nova-ws-url-hint");
    if (el) {
      el.textContent = computeWsUrl();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", update);
  } else {
    update();
  }
})();
