document.addEventListener("DOMContentLoaded", function () {
    const userPage = document.querySelector(".admin-user-management-page");
    const selectedCardContainer = document.getElementById("admin-selected-user-card-container");

    if (!userPage || !selectedCardContainer) {
        return;
    }

    let activeRequestController = null;

    function updateSelectedRowState(selectedUserId) {
        const rows = userPage.querySelectorAll(".admin-user-table tbody tr[data-user-id]");

        rows.forEach(function (row) {
            const rowUserId = row.getAttribute("data-user-id") || "";
            const isSelected = rowUserId === String(selectedUserId);
            const selectButton = row.querySelector(".admin-select-user-button");

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

    function updateBrowserUrl(selectedUserId) {
        const nextUrl = new URL(window.location.href);

        if (selectedUserId) {
            nextUrl.searchParams.set("selected", String(selectedUserId));
        } else {
            nextUrl.searchParams.delete("selected");
        }

        window.history.replaceState({}, "", nextUrl.toString());
    }

    async function loadSelectedUserCard(triggerElement) {
        const selectedCardUrl = triggerElement.getAttribute("data-selected-card-url") || "";
        const selectedUserId = triggerElement.getAttribute("data-user-id") || "";

        if (selectedCardUrl === "" || selectedUserId === "") {
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
                throw new Error("Selected user card request failed.");
            }

            const html = await response.text();
            selectedCardContainer.innerHTML = html;
            updateSelectedRowState(selectedUserId);
            updateBrowserUrl(selectedUserId);
        } catch (error) {
            if (error.name !== "AbortError") {
                window.location.assign(triggerElement.getAttribute("href") || window.location.href);
            }
        } finally {
            selectedCardContainer.setAttribute("aria-busy", "false");
            selectedCardContainer.classList.remove("admin-selected-card-loading");
        }
    }

    userPage.addEventListener("click", function (event) {
        const selectButton = event.target.closest(".admin-select-user-button");
        if (!selectButton) {
            return;
        }

        if (selectButton.classList.contains("disabled")) {
            event.preventDefault();
            return;
        }

        event.preventDefault();
        loadSelectedUserCard(selectButton);
    });
});
