document.addEventListener("DOMContentLoaded", function () {
    const dashboardPage = document.querySelector(".admin-dashboard-page");
    if (!dashboardPage || typeof bootstrap === "undefined") {
        return;
    }

    const tooltipTriggerList = dashboardPage.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltipTriggerList.forEach(function (tooltipTriggerElement) {
        bootstrap.Tooltip.getOrCreateInstance(tooltipTriggerElement);
    });

    const startInput = dashboardPage.querySelector("#id_start_date");
    const endInput = dashboardPage.querySelector("#id_end_date");

    function syncDateInputConstraints() {
        if (startInput && endInput) {
            if (startInput.value) {
                endInput.min = startInput.value;
            }
            if (endInput.value) {
                startInput.max = endInput.value;
            }
        }
    }

    if (startInput && endInput) {
        syncDateInputConstraints();
        startInput.addEventListener("change", syncDateInputConstraints);
        endInput.addEventListener("change", syncDateInputConstraints);
    }
});
