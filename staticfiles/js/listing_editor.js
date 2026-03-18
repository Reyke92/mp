document.addEventListener("DOMContentLoaded", function () {
    const formElement = document.querySelector("form[data-listing-editor='true']");
    if (formElement === null) {
        attachDeleteListingConfirmation();
        return;
    }

    const categoryField = document.getElementById("id_category");
    const stateField = document.getElementById("id_state");
    const citySuggestionsElement = document.getElementById("city-suggestions");
    const attributeRegion = document.getElementById("category-attributes-region");
    const descriptionField = document.getElementById("id_description");
    const descriptionCharacterCountElement = document.getElementById("description-character-count");
    const imageInput = document.getElementById("id_images");
    const imageListElement = document.getElementById("listing-image-list");
    const imageEmptyStateElement = document.getElementById("listing-image-empty-state");
    const hiddenInputsContainer = document.getElementById("listing-editor-hidden-inputs");
    const openImagePickerButton = document.getElementById("open-image-picker-button");
    const clearImageListButton = document.getElementById("clear-image-list-button");
    const existingImagesScript = document.getElementById("listing-editor-existing-images");

    const imageState = {
        items: [],
        nextNewToken: 0,
        removedExistingIds: new Set(),
    };

    function parseExistingImages() {
        if (existingImagesScript === null) {
            return [];
        }

        try {
            const payload = JSON.parse(existingImagesScript.textContent || "[]");
            return Array.isArray(payload) ? payload : [];
        } catch (error) {
            return [];
        }
    }

    function initializeExistingImages() {
        const existingImages = parseExistingImages();
        imageState.items = existingImages.map(function (image) {
            return {
                kind: "existing",
                id: Number(image.id),
                url: String(image.url || ""),
                name: String(image.name || "Existing image"),
            };
        });
    }

    function syncDescriptionCount() {
        if (descriptionField === null || descriptionCharacterCountElement === null) {
            return;
        }
        descriptionCharacterCountElement.textContent = `${descriptionField.value.length} / ${descriptionField.getAttribute("maxlength")}`;
    }

    async function refreshCategoryAttributes() {
        if (categoryField === null || attributeRegion === null) {
            return;
        }

        const url = new URL(formElement.dataset.attributeFieldsUrl, window.location.origin);
        if (categoryField.value !== "") {
            url.searchParams.set("category", categoryField.value);
        }

        const response = await fetch(url, {
            headers: {
                "X-Requested-With": "XMLHttpRequest",
            },
            credentials: "same-origin",
        });

        if (!response.ok) {
            return;
        }

        attributeRegion.innerHTML = await response.text();
    }

    async function refreshCitySuggestions() {
        if (stateField === null || citySuggestionsElement === null) {
            return;
        }

        citySuggestionsElement.innerHTML = "";
        if (stateField.value === "") {
            return;
        }

        const url = new URL(formElement.dataset.stateCitiesUrl, window.location.origin);
        url.searchParams.set("state_id", stateField.value);

        const response = await fetch(url, {
            headers: {
                "X-Requested-With": "XMLHttpRequest",
            },
            credentials: "same-origin",
        });

        if (!response.ok) {
            return;
        }

        const payload = await response.json();
        const cities = Array.isArray(payload.cities) ? payload.cities : [];
        cities.forEach(function (cityName) {
            const optionElement = document.createElement("option");
            optionElement.value = cityName;
            citySuggestionsElement.appendChild(optionElement);
        });
    }

    function syncFileInputFromState() {
        if (imageInput === null) {
            return;
        }

        const dataTransfer = new DataTransfer();
        imageState.items.forEach(function (item) {
            if (item.kind === "new") {
                dataTransfer.items.add(item.file);
            }
        });
        imageInput.files = dataTransfer.files;
    }

    function buildImageOrderMetadata() {
        const newIndexByToken = new Map();
        let newIndex = 0;
        imageState.items.forEach(function (item) {
            if (item.kind === "new") {
                newIndexByToken.set(item.token, newIndex);
                newIndex += 1;
            }
        });

        const imageOrder = imageState.items.map(function (item) {
            if (item.kind === "existing") {
                return `existing:${item.id}`;
            }
            return `new:${newIndexByToken.get(item.token)}`;
        });

        return {
            imageOrder,
            removedExistingIds: Array.from(imageState.removedExistingIds.values()),
        };
    }

    function syncHiddenInputs() {
        if (hiddenInputsContainer === null) {
            return;
        }

        hiddenInputsContainer.innerHTML = "";
        const metadata = buildImageOrderMetadata();

        metadata.imageOrder.forEach(function (value) {
            const inputElement = document.createElement("input");
            inputElement.type = "hidden";
            inputElement.name = "image_order";
            inputElement.value = value;
            hiddenInputsContainer.appendChild(inputElement);
        });

        metadata.removedExistingIds.forEach(function (imageId) {
            const inputElement = document.createElement("input");
            inputElement.type = "hidden";
            inputElement.name = "removed_existing_image_ids";
            inputElement.value = String(imageId);
            hiddenInputsContainer.appendChild(inputElement);
        });
    }

    function makeImagePreviewRow(item, index) {
        const rowElement = document.createElement("div");
        rowElement.className = "image-preview-row";

        const previewElement = document.createElement(item.url ? "img" : "div");
        if (item.url) {
            previewElement.src = item.url;
            previewElement.alt = item.name;
            previewElement.className = "image-preview-thumb";
        } else {
            previewElement.className = "image-preview-thumb image-preview-thumb-placeholder d-flex align-items-center justify-content-center text-body-secondary small";
            previewElement.textContent = "New";
        }
        rowElement.appendChild(previewElement);

        const infoElement = document.createElement("div");
        infoElement.className = "image-preview-info";

        const nameElement = document.createElement("div");
        nameElement.className = "fw-semibold text-truncate";
        nameElement.textContent = item.name;
        infoElement.appendChild(nameElement);

        const metaElement = document.createElement("div");
        metaElement.className = "small text-body-secondary d-flex flex-wrap gap-2 mt-1";
        const positionBadge = document.createElement("span");
        positionBadge.className = "badge text-bg-light border";
        positionBadge.textContent = `Position ${index + 1}`;
        metaElement.appendChild(positionBadge);

        const sourceBadge = document.createElement("span");
        sourceBadge.className = item.kind === "existing" ? "badge text-bg-secondary-subtle border" : "badge text-bg-primary-subtle border";
        sourceBadge.textContent = item.kind === "existing" ? "Existing" : "New";
        metaElement.appendChild(sourceBadge);
        infoElement.appendChild(metaElement);
        rowElement.appendChild(infoElement);

        const actionsElement = document.createElement("div");
        actionsElement.className = "image-preview-actions";

        const moveUpButton = document.createElement("button");
        moveUpButton.type = "button";
        moveUpButton.className = "btn btn-outline-secondary btn-sm";
        moveUpButton.textContent = "Move up";
        moveUpButton.disabled = index === 0;
        moveUpButton.addEventListener("click", function () {
            if (index === 0) {
                return;
            }
            const currentItem = imageState.items[index];
            imageState.items[index] = imageState.items[index - 1];
            imageState.items[index - 1] = currentItem;
            renderImageList();
        });
        actionsElement.appendChild(moveUpButton);

        const moveDownButton = document.createElement("button");
        moveDownButton.type = "button";
        moveDownButton.className = "btn btn-outline-secondary btn-sm";
        moveDownButton.textContent = "Move down";
        moveDownButton.disabled = index === (imageState.items.length - 1);
        moveDownButton.addEventListener("click", function () {
            if (index >= imageState.items.length - 1) {
                return;
            }
            const currentItem = imageState.items[index];
            imageState.items[index] = imageState.items[index + 1];
            imageState.items[index + 1] = currentItem;
            renderImageList();
        });
        actionsElement.appendChild(moveDownButton);

        const removeButton = document.createElement("button");
        removeButton.type = "button";
        removeButton.className = "btn btn-outline-danger btn-sm";
        removeButton.textContent = "Remove";
        removeButton.addEventListener("click", function () {
            const removedItem = imageState.items.splice(index, 1)[0];
            if (removedItem.kind === "existing") {
                imageState.removedExistingIds.add(removedItem.id);
            }
            renderImageList();
        });
        actionsElement.appendChild(removeButton);

        rowElement.appendChild(actionsElement);
        return rowElement;
    }

    function renderImageList() {
        if (imageListElement === null || imageEmptyStateElement === null) {
            return;
        }

        syncFileInputFromState();
        syncHiddenInputs();
        imageListElement.innerHTML = "";

        if (imageState.items.length === 0) {
            imageListElement.appendChild(imageEmptyStateElement);
            imageEmptyStateElement.classList.remove("d-none");
            return;
        }

        imageEmptyStateElement.classList.add("d-none");
        imageState.items.forEach(function (item, index) {
            imageListElement.appendChild(makeImagePreviewRow(item, index));
        });
    }

    function handleChosenImages() {
        if (imageInput === null) {
            return;
        }

        const newFiles = Array.from(imageInput.files || []);
        newFiles.forEach(function (file) {
            imageState.items.push({
                kind: "new",
                token: imageState.nextNewToken,
                file,
                url: URL.createObjectURL(file),
                name: file.name,
            });
            imageState.nextNewToken += 1;
        });
        renderImageList();
    }

    function clearAllImages() {
        imageState.items.forEach(function (item) {
            if (item.kind === "existing") {
                imageState.removedExistingIds.add(item.id);
            }
        });
        imageState.items = [];
        renderImageList();
    }

    if (descriptionField !== null) {
        descriptionField.addEventListener("input", syncDescriptionCount);
        syncDescriptionCount();
    }

    if (categoryField !== null) {
        categoryField.addEventListener("change", function () {
            refreshCategoryAttributes();
        });
    }

    if (stateField !== null) {
        stateField.addEventListener("change", function () {
            refreshCitySuggestions();
        });
    }

    if (imageInput !== null) {
        imageInput.addEventListener("change", handleChosenImages);
    }

    if (openImagePickerButton !== null && imageInput !== null) {
        openImagePickerButton.addEventListener("click", function () {
            imageInput.click();
        });
    }

    if (clearImageListButton !== null) {
        clearImageListButton.addEventListener("click", clearAllImages);
    }

    formElement.addEventListener("submit", function () {
        syncFileInputFromState();
        syncHiddenInputs();
    });

    initializeExistingImages();
    renderImageList();
    attachDeleteListingConfirmation();
});

function attachDeleteListingConfirmation() {
    document.querySelectorAll("form[data-delete-listing-form='true']").forEach(function (formElement) {
        if (formElement.dataset.confirmBound === "true") {
            return;
        }
        formElement.dataset.confirmBound = "true";
        formElement.addEventListener("submit", function (event) {
            const shouldDelete = window.confirm("Delete this listing? This will mark it as Deleted and remove it from your My Listings view.");
            if (!shouldDelete) {
                event.preventDefault();
            }
        });
    });
}
