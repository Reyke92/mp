document.addEventListener("DOMContentLoaded", function () {
    const listingPage = document.querySelector(".admin-listing-management-page");
    const selectedCardContainer = document.getElementById("admin-selected-listing-card-container");

    if (!listingPage || !selectedCardContainer) {
        return;
    }

    let activeRequestController = null;

    function updateSelectedRowState(selectedListingId) {
        const rows = listingPage.querySelectorAll(".admin-listing-table tbody tr[data-listing-id]");

        rows.forEach(function (row) {
            const rowListingId = row.getAttribute("data-listing-id") || "";
            const isSelected = rowListingId === String(selectedListingId);
            const selectButton = row.querySelector(".admin-select-listing-button");

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

    function updateBrowserUrl(selectedListingId) {
        const nextUrl = new URL(window.location.href);

        if (selectedListingId) {
            nextUrl.searchParams.set("selected", String(selectedListingId));
        } else {
            nextUrl.searchParams.delete("selected");
        }

        window.history.replaceState({}, "", nextUrl.toString());
    }

    async function loadSelectedListingCard(triggerElement) {
        const selectedCardUrl = triggerElement.getAttribute("data-selected-card-url") || "";
        const selectedListingId = triggerElement.getAttribute("data-listing-id") || "";

        if (selectedCardUrl === "" || selectedListingId === "") {
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
                throw new Error("Selected listing card request failed.");
            }

            const html = await response.text();
            selectedCardContainer.innerHTML = html;
            updateSelectedRowState(selectedListingId);
            updateBrowserUrl(selectedListingId);
        } catch (error) {
            if (error.name !== "AbortError") {
                window.location.assign(triggerElement.getAttribute("href") || window.location.href);
            }
        } finally {
            selectedCardContainer.setAttribute("aria-busy", "false");
            selectedCardContainer.classList.remove("admin-selected-card-loading");
        }
    }

    listingPage.addEventListener("click", function (event) {
        const selectButton = event.target.closest(".admin-select-listing-button");
        if (!selectButton) {
            return;
        }

        if (selectButton.classList.contains("disabled")) {
            event.preventDefault();
            return;
        }

        event.preventDefault();
        loadSelectedListingCard(selectButton);
    });

    listingPage.addEventListener("click", async function (event) {
        const copyButton = event.target.closest(".admin-copy-email-button");
        if (!copyButton) {
            return;
        }

        const copyValue = copyButton.getAttribute("data-copy-value") || "";
        const defaultLabel = copyButton.getAttribute("data-default-label") || "Copy";
        const labelSpan = copyButton.querySelector("span span");

        if (copyValue === "") {
            return;
        }

        try {
            await navigator.clipboard.writeText(copyValue);
            if (labelSpan) {
                labelSpan.textContent = "Copied";
            }
        } catch (error) {
            if (labelSpan) {
                labelSpan.textContent = "Copy Failed";
            }
        }

        window.setTimeout(function () {
            if (labelSpan) {
                labelSpan.textContent = defaultLabel;
            }
        }, 1500);
    });
});
