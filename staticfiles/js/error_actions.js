(function () {
  "use strict";

  function isSameOriginReferrer() {
    if (!document.referrer) {
      return false;
    }

    try {
      return new URL(document.referrer).origin === window.location.origin;
    } catch (error) {
      return false;
    }
  }

  document.addEventListener("click", function (event) {
    var trigger = event.target.closest("[data-error-action='go-back']");

    if (!trigger) {
      return;
    }

    event.preventDefault();

    var homeUrl = trigger.getAttribute("data-home-url") || "/";

    if (window.history.length > 1 && isSameOriginReferrer()) {
      window.history.back();
      return;
    }

    window.location.assign(homeUrl);
  });
})();
