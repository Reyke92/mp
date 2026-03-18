document.addEventListener("DOMContentLoaded", function () {
    const payloadElement = document.getElementById("listing-detail-gallery-images");
    const focusRegion = document.getElementById("listing-gallery-focus-region");
    const thumbnailRegion = document.getElementById("listing-gallery-thumbnail-region");
    const emptyStateElement = document.getElementById("listing-gallery-empty-state");
    const openModalButton = document.getElementById("listing-gallery-open-modal-button");
    const modalElement = document.getElementById("listing-gallery-modal");
    const modalStageElement = document.getElementById("listing-gallery-modal-stage");
    const modalImageElement = document.getElementById("listing-gallery-modal-image");
    const modalCounterElement = document.getElementById("listing-gallery-modal-counter");
    const modalPreviousButton = document.getElementById("listing-gallery-modal-prev");
    const modalNextButton = document.getElementById("listing-gallery-modal-next");
    const modalResetZoomButton = document.getElementById("listing-gallery-modal-reset-zoom");

    if (
        payloadElement === null ||
        focusRegion === null ||
        thumbnailRegion === null ||
        emptyStateElement === null ||
        openModalButton === null ||
        modalElement === null ||
        modalStageElement === null ||
        modalImageElement === null ||
        modalCounterElement === null ||
        modalPreviousButton === null ||
        modalNextButton === null ||
        modalResetZoomButton === null
    ) {
        return;
    }

    let images = [];
    try {
        const parsedPayload = JSON.parse(payloadElement.textContent || "[]");
        if (Array.isArray(parsedPayload)) {
            images = parsedPayload.filter(function (entry) {
                return typeof entry === "object" && entry !== null && typeof entry.url === "string";
            });
        }
    } catch (error) {
        images = [];
    }

    if (images.length === 0) {
        emptyStateElement.classList.remove("d-none");
        focusRegion.classList.add("d-none");
        thumbnailRegion.classList.add("d-none");
        openModalButton.classList.add("d-none");
        return;
    }

    emptyStateElement.classList.add("d-none");
    focusRegion.classList.remove("d-none");
    thumbnailRegion.classList.remove("d-none");
    openModalButton.classList.remove("d-none");

    const galleryModal = bootstrap.Modal.getOrCreateInstance(modalElement);
    const finePointerQuery = window.matchMedia("(pointer: fine)");
    const state = {
        activeIndex: 0,
        zoomScale: 1,
        translateX: 0,
        translateY: 0,
        isDragging: false,
        dragStartX: 0,
        dragStartY: 0,
        baseTranslateX: 0,
        baseTranslateY: 0,
        pointerModeEnabled: finePointerQuery.matches,
    };

    function preventNativeImageDrag(event) {
        event.preventDefault();
    }

    function getSafeIndex(index) {
        if (images.length === 0) {
            return 0;
        }
        if (index < 0) {
            return images.length - 1;
        }
        if (index >= images.length) {
            return 0;
        }
        return index;
    }

    function clampTranslation(value, maxOffset) {
        if (maxOffset <= 0) {
            return 0;
        }
        return Math.max(-maxOffset, Math.min(maxOffset, value));
    }

    function getTranslationBounds() {
        if (state.zoomScale <= 1) {
            return { maxX: 0, maxY: 0 };
        }
        const rect = modalStageElement.getBoundingClientRect();
        return {
            maxX: ((state.zoomScale - 1) * rect.width) / 2,
            maxY: ((state.zoomScale - 1) * rect.height) / 2,
        };
    }

    function updateZoomUi() {
        modalStageElement.classList.toggle("is-zoomed", state.zoomScale > 1);
        modalStageElement.classList.toggle("is-dragging", state.isDragging);
        modalResetZoomButton.classList.toggle("d-none", state.zoomScale <= 1);
    }

    function applyZoomTransform() {
        modalImageElement.style.transform = `translate(${state.translateX}px, ${state.translateY}px) scale(${state.zoomScale})`;
        updateZoomUi();
    }

    function resetZoom() {
        state.zoomScale = 1;
        state.translateX = 0;
        state.translateY = 0;
        state.isDragging = false;
        applyZoomTransform();
    }

    function setZoomScale(nextScale, anchorPoint) {
        const clampedScale = Math.max(1, Math.min(4, nextScale));
        const previousScale = state.zoomScale;

        if (clampedScale === 1) {
            resetZoom();
            return;
        }

        if (anchorPoint !== undefined && previousScale !== clampedScale) {
            const rect = modalStageElement.getBoundingClientRect();
            const offsetX = anchorPoint.clientX - rect.left - rect.width / 2;
            const offsetY = anchorPoint.clientY - rect.top - rect.height / 2;
            const scaleRatio = clampedScale / previousScale;
            state.translateX = (state.translateX - offsetX) * scaleRatio + offsetX;
            state.translateY = (state.translateY - offsetY) * scaleRatio + offsetY;
        }

        state.zoomScale = clampedScale;
        const bounds = getTranslationBounds();
        state.translateX = clampTranslation(state.translateX, bounds.maxX);
        state.translateY = clampTranslation(state.translateY, bounds.maxY);
        applyZoomTransform();
    }

    function zoomInAtPoint(anchorPoint) {
        if (!state.pointerModeEnabled) {
            return;
        }
        if (state.zoomScale > 1) {
            return;
        }
        setZoomScale(2.25, anchorPoint);
    }

    function setActiveIndex(nextIndex) {
        state.activeIndex = getSafeIndex(nextIndex);
        renderGallery();
        renderModalImage();
        resetZoom();
    }

    function openModal() {
        renderModalImage();
        galleryModal.show();
    }

    function createControlButton(direction, onClick) {
        const buttonElement = document.createElement("button");
        buttonElement.type = "button";
        buttonElement.className = `listing-gallery-control listing-gallery-control-${direction}`;
        buttonElement.setAttribute("aria-label", direction === "prev" ? "Previous image" : "Next image");
        buttonElement.innerHTML = `<span aria-hidden="true">${direction === "prev" ? "‹" : "›"}</span>`;
        buttonElement.addEventListener("click", onClick);
        return buttonElement;
    }

    function renderFocusImage() {
        const activeImage = images[state.activeIndex];
        focusRegion.innerHTML = "";

        const stageElement = document.createElement("div");
        stageElement.className = "listing-gallery-stage";

        const imageButton = document.createElement("button");
        imageButton.type = "button";
        imageButton.className = "listing-gallery-focus-button";
        imageButton.setAttribute("aria-label", "Open this image in the full-size viewer");
        imageButton.addEventListener("click", openModal);

        const imageElement = document.createElement("img");
        imageElement.className = "listing-gallery-focus-image";
        imageElement.draggable = false;
        imageElement.src = activeImage.url;
        imageElement.alt = activeImage.alt || "Listing image";
        imageButton.appendChild(imageElement);
        stageElement.appendChild(imageButton);

        const toolbarElement = document.createElement("div");
        toolbarElement.className = "listing-gallery-toolbar";

        const counterElement = document.createElement("div");
        counterElement.className = "listing-gallery-counter";
        counterElement.textContent = `Image ${state.activeIndex + 1} of ${images.length}`;
        toolbarElement.appendChild(counterElement);

        const fullscreenButton = document.createElement("button");
        fullscreenButton.type = "button";
        fullscreenButton.className = "btn btn-sm btn-outline-secondary listing-gallery-fullsize-button";
        fullscreenButton.textContent = "Full size";
        fullscreenButton.addEventListener("click", openModal);
        toolbarElement.appendChild(fullscreenButton);
        stageElement.appendChild(toolbarElement);

        if (images.length > 1) {
            stageElement.appendChild(
                createControlButton("prev", function () {
                    setActiveIndex(state.activeIndex - 1);
                })
            );
            stageElement.appendChild(
                createControlButton("next", function () {
                    setActiveIndex(state.activeIndex + 1);
                })
            );
        }

        focusRegion.appendChild(stageElement);
    }

    function renderThumbnails() {
        thumbnailRegion.innerHTML = "";

        const listElement = document.createElement("div");
        listElement.className = "listing-gallery-thumbnails";

        images.forEach(function (image, index) {
            const buttonElement = document.createElement("button");
            buttonElement.type = "button";
            buttonElement.className = "listing-gallery-thumbnail";
            if (index === state.activeIndex) {
                buttonElement.classList.add("active");
                buttonElement.setAttribute("aria-current", "true");
            }
            buttonElement.setAttribute("aria-label", `Show image ${index + 1}`);
            buttonElement.addEventListener("click", function () {
                setActiveIndex(index);
            });

            const thumbnailImage = document.createElement("img");
            thumbnailImage.draggable = false;
            thumbnailImage.src = image.url;
            thumbnailImage.alt = image.alt || `Listing image ${index + 1}`;
            thumbnailImage.loading = "lazy";
            buttonElement.appendChild(thumbnailImage);

            listElement.appendChild(buttonElement);
        });

        thumbnailRegion.appendChild(listElement);
    }

    function renderModalImage() {
        const activeImage = images[state.activeIndex];
        modalImageElement.draggable = false;
        modalImageElement.src = activeImage.url;
        modalImageElement.alt = activeImage.alt || "Listing image";
        modalCounterElement.textContent = `Image ${state.activeIndex + 1} of ${images.length}`;
    }

    function renderGallery() {
        renderFocusImage();
        renderThumbnails();
    }

    modalImageElement.addEventListener("dragstart", preventNativeImageDrag);
    modalImageElement.addEventListener("mousedown", function (event) {
        if (state.pointerModeEnabled && state.zoomScale > 1) {
            event.preventDefault();
        }
    });

    openModalButton.addEventListener("click", openModal);
    modalPreviousButton.addEventListener("click", function () {
        setActiveIndex(state.activeIndex - 1);
    });
    modalNextButton.addEventListener("click", function () {
        setActiveIndex(state.activeIndex + 1);
    });
    modalResetZoomButton.addEventListener("click", resetZoom);

    finePointerQuery.addEventListener("change", function (event) {
        state.pointerModeEnabled = event.matches;
        resetZoom();
    });

    modalStageElement.addEventListener("click", function (event) {
        if (!state.pointerModeEnabled || state.isDragging) {
            return;
        }
        if (event.target !== modalImageElement) {
            return;
        }
        zoomInAtPoint(event);
    });

    modalStageElement.addEventListener("dblclick", function (event) {
        if (!state.pointerModeEnabled) {
            return;
        }
        event.preventDefault();
        resetZoom();
    });

    modalStageElement.addEventListener(
        "wheel",
        function (event) {
            if (!state.pointerModeEnabled) {
                return;
            }
            event.preventDefault();
            const nextScale = event.deltaY < 0 ? state.zoomScale + 0.25 : state.zoomScale - 0.25;
            setZoomScale(nextScale, event);
        },
        { passive: false }
    );

    modalStageElement.addEventListener("pointerdown", function (event) {
        if (!state.pointerModeEnabled || state.zoomScale <= 1 || event.target !== modalImageElement) {
            return;
        }
        event.preventDefault();
        state.isDragging = true;
        state.dragStartX = event.clientX;
        state.dragStartY = event.clientY;
        state.baseTranslateX = state.translateX;
        state.baseTranslateY = state.translateY;
        modalStageElement.setPointerCapture(event.pointerId);
        updateZoomUi();
    });

    modalStageElement.addEventListener("pointermove", function (event) {
        if (!state.pointerModeEnabled || !state.isDragging) {
            return;
        }
        const bounds = getTranslationBounds();
        const deltaX = event.clientX - state.dragStartX;
        const deltaY = event.clientY - state.dragStartY;
        state.translateX = clampTranslation(state.baseTranslateX + deltaX, bounds.maxX);
        state.translateY = clampTranslation(state.baseTranslateY + deltaY, bounds.maxY);
        applyZoomTransform();
    });

    function stopDragging(event) {
        if (!state.isDragging) {
            return;
        }
        state.isDragging = false;
        if (event && modalStageElement.hasPointerCapture(event.pointerId)) {
            modalStageElement.releasePointerCapture(event.pointerId);
        }
        updateZoomUi();
    }

    modalStageElement.addEventListener("pointerup", stopDragging);
    modalStageElement.addEventListener("pointercancel", stopDragging);
    modalStageElement.addEventListener("pointerleave", function () {
        if (!state.isDragging) {
            return;
        }
        updateZoomUi();
    });

    modalElement.addEventListener("hidden.bs.modal", function () {
        resetZoom();
    });

    document.addEventListener("keydown", function (event) {
        if (!modalElement.classList.contains("show")) {
            return;
        }
        if (event.key === "ArrowLeft") {
            event.preventDefault();
            setActiveIndex(state.activeIndex - 1);
        }
        if (event.key === "ArrowRight") {
            event.preventDefault();
            setActiveIndex(state.activeIndex + 1);
        }
        if (event.key === "Escape") {
            resetZoom();
        }
    });

    renderGallery();
    renderModalImage();
    resetZoom();
});
