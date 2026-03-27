/**
 * Mirror console.log / info / warn / error into the dashboard panel `#nova-console`.
 *
 * Args:
 *   None (runs once at load; expects `#nova-console`, optional clear/copy buttons).
 *
 * Returns:
 *   undefined
 *
 * Example:
 *   Loaded with defer after dashboard DOM: <script src="/static/js/nova_console_panel.js" defer></script>
 */
(function () {
  "use strict";

  var panel = document.getElementById("nova-console");
  var clearBtn = document.getElementById("nova-console-clear");
  var copyBtn = document.getElementById("nova-console-copy");
  if (!panel) {
    return;
  }

  function appendLine(kind, args) {
    var line = document.createElement("div");
    line.className = "console-line console-line-" + kind;
    var text = Array.prototype.map.call(args, function (a) {
      try {
        if (typeof a === "object") {
          return JSON.stringify(a);
        }
        return String(a);
      } catch (_) {
        return String(a);
      }
    }).join(" ");
    line.textContent = "[" + kind.toUpperCase() + "] " + text;
    panel.appendChild(line);
    panel.scrollTop = panel.scrollHeight;
  }

  var origLog = console.log;
  var origInfo = console.info;
  var origWarn = console.warn;
  var origError = console.error;

  console.log = function () {
    appendLine("log", arguments);
    return origLog && origLog.apply(console, arguments);
  };
  console.info = function () {
    appendLine("info", arguments);
    return origInfo && origInfo.apply(console, arguments);
  };
  console.warn = function () {
    appendLine("warn", arguments);
    return origWarn && origWarn.apply(console, arguments);
  };
  console.error = function () {
    appendLine("error", arguments);
    return origError && origError.apply(console, arguments);
  };

  if (clearBtn) {
    clearBtn.addEventListener("click", function () {
      panel.innerHTML = "";
    });
  }

  if (copyBtn && navigator.clipboard && navigator.clipboard.writeText) {
    copyBtn.addEventListener("click", function () {
      var text = panel.innerText || panel.textContent || "";
      navigator.clipboard.writeText(text).catch(function (err) {
        console.error("Failed to copy console text", err);
      });
    });
  }
})();
