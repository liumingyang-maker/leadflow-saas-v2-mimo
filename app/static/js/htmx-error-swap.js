(function () {
  "use strict";

  document.addEventListener("htmx:beforeSwap", function (event) {
    var xhr = event.detail && event.detail.xhr;
    if (!xhr || xhr.getResponseHeader("HX-LeadFlow-Swap-Error") !== "true") {
      return;
    }
    event.detail.shouldSwap = true;
    event.detail.isError = false;
  });
})();
