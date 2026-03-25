(function () {
  "use strict";

  var btn = document.getElementById("focus-play");
  if (!btn) return;

  btn.addEventListener("click", function () {
    var text = btn.getAttribute("data-focus-summary") || "";
    if (!text.trim()) return;
    if (window.Nova && typeof window.Nova.sendText === "function") {
      window.Nova.sendText(text);
    } else {
      console.error("Nova.sendText not available");
    }
  });
})();
