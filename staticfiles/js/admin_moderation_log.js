document.addEventListener("DOMContentLoaded", function () {
    const moderationLogPage = document.querySelector(".admin-moderation-log-page");
    const selectedCardContainer = document.getElementById("admin-selected-moderation-report-card-container");

    if (!moderationLogPage || !selectedCardContainer) {
        return;
    }

    let activeRequestController = null;

    function updateSelectedRowState(selectedActionId) {
        const rows = moderationLogPage.querySelectorAll(".admin-moderation-table tbody tr[data-action-id]");

        rows.forEach(function (row) {
            const rowActionId = row.getAttribute("data-action-id") || "";
            const isSelected = rowActionId === String(selectedActionId);
            const selectButton = row.querySelector(".admin-select-moderation-action-button");

            row.classList.toggle("admin-user-table-row-selected", isSelected);

            if (!selectButton) {
                return;
            }

            const selectLabel = selectButton.getAttribute("data-select-label") || "Select";
            const selectedLabel = selectButton.getAttribute("data-selected-label") || "Selected";

            if (isSelected) {
                selectButton.classList.remove("btn-outline-primary");
                selectButton.classList.add("btn-primary", "disabled");
                selectButton.setAttribute("aria-disabled", "true");
                selectButton.setAttribute("tabindex", "-1");
                selectButton.textContent = selectedLabel;
            } else {
                selectButton.classList.remove("btn-primary", "disabled");
                selectButton.classList.add("btn-outline-primary");
                selectButton.removeAttribute("aria-disabled");
                selectButton.removeAttribute("tabindex");
                selectButton.textContent = selectLabel;
            }
        });
    }

    function updateBrowserUrl(selectedActionId) {
        const nextUrl = new URL(window.location.href);

        if (selectedActionId) {
            nextUrl.searchParams.set("selected", String(selectedActionId));
        } else {
            nextUrl.searchParams.delete("selected");
        }

        window.history.replaceState({}, "", nextUrl.toString());
    }

    async function loadSelectedReportCard(triggerElement) {
        const selectedCardUrl = triggerElement.getAttribute("data-selected-card-url") || "";
        const selectedActionId = triggerElement.getAttribute("data-action-id") || "";

        if (selectedCardUrl === "" || selectedActionId === "") {
            window.location.assign(triggerElement.getAttribute("href") || window.location.href);
            return;
        }

        if (activeRequestController !== null) {
            activeRequestController.abort();
        }

        activeRequestController = new AbortController();
        selectedCardContainer.setAttribute("aria-busy", "true");
        selectedCardContainer.classList.add("admin-selected-card-loading");

        try {
            const response = await fetch(selectedCardUrl, {
                method: "GET",
                headers: {
                    "X-Requested-With": "XMLHttpRequest"
                },
                signal: activeRequestController.signal
            });

            if (!response.ok) {
                throw new Error("Selected moderation report request failed.");
            }

            const html = await response.text();
            selectedCardContainer.innerHTML = html;
            updateSelectedRowState(selectedActionId);
            updateBrowserUrl(selectedActionId);
        } catch (error) {
            if (error.name !== "AbortError") {
                window.location.assign(triggerElement.getAttribute("href") || window.location.href);
            }
        } finally {
            selectedCardContainer.setAttribute("aria-busy", "false");
            selectedCardContainer.classList.remove("admin-selected-card-loading");
        }
    }

    moderationLogPage.addEventListener("click", function (event) {
        const selectButton = event.target.closest(".admin-select-moderation-action-button");
        if (!selectButton) {
            return;
        }

        if (selectButton.classList.contains("disabled")) {
            event.preventDefault();
            return;
        }

        event.preventDefault();
        loadSelectedReportCard(selectButton);
    });
});
