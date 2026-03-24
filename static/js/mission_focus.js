(function () {
  "use strict";

  var btn = document.getElementById("focus-play");
  if (!btn) return;

  function getCookie(name) {
    var cookieValue = null;
    if (document.cookie && document.cookie !== "") {
      var cookies = document.cookie.split(";");
      for (var i = 0; i < cookies.length; i++) {
        var cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === name + "=") {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  btn.addEventListener("click", function () {
    var text = btn.getAttribute("data-focus-summary") || "";
    if (!text.trim()) return;
    var csrftoken = getCookie("csrftoken");
    fetch("/api/nova/voice/", {
      method: "POST",
      headers: {
        "X-CSRFToken": csrftoken,
      },
      body: new URLSearchParams({ text: text }),
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (data && data.audio_url) {
          var audio = new Audio(data.audio_url);
          audio.play().catch(function () {});
        }
      })
      .catch(function (err) {
        console.error("Nova focus summary error", err);
      });
  });
})();
