/**
 * Curio Tracking Page
 * - Modal (add/edit entry)
 * - Set filters (client-side)
 * - Image preview
 * - CRUD API calls
 * - "Other" set conditional input
 */

(function () {
  "use strict";

  // --- Filter Logic ---

  const filterBtns = document.querySelectorAll(".curio-filter-btn");
  const entries = document.querySelectorAll(".curio-entry");

  filterBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      // Toggle active state
      filterBtns.forEach((b) => b.classList.remove("curio-filter-btn--active"));
      btn.classList.add("curio-filter-btn--active");

      const setId = btn.getAttribute("data-set-id");

      entries.forEach((entry) => {
        if (setId === "all" || entry.getAttribute("data-set-id") === setId) {
          entry.classList.remove("curio-entry--hidden");
        } else {
          entry.classList.add("curio-entry--hidden");
        }
      });
    });
  });

  // --- Modal Logic (admin only) ---

  const modal = document.getElementById("curio-modal");
  if (!modal) return; // Not admin — no modal exists

  const modalTitle = document.getElementById("curio-modal-title");
  const modalBackdrop = document.getElementById("curio-modal-backdrop");
  const modalClose = document.getElementById("curio-modal-close");
  const modalCancel = document.getElementById("curio-modal-cancel");
  const modalSubmit = document.getElementById("curio-modal-submit");
  const addBtn = document.getElementById("add-entry-btn");

  const form = document.getElementById("curio-form");
  const entryIdField = document.getElementById("curio-entry-id");
  const nameField = document.getElementById("curio-name");
  const numberPulledField = document.getElementById("curio-number-pulled");
  const descriptionField = document.getElementById("curio-description");
  const setField = document.getElementById("curio-set");
  const customSetField = document.getElementById("custom-set-field");
  const customSetInput = document.getElementById("curio-custom-set");
  const imageField = document.getElementById("curio-image");
  const imagePreview = document.getElementById("image-preview");
  const imagePreviewImg = document.getElementById("image-preview-img");

  function openModal(title) {
    modalTitle.textContent = title;
    modal.style.display = "flex";
    // Trigger animation
    requestAnimationFrame(() => {
      modal.classList.add("modal--active");
    });
  }

  function closeModal() {
    modal.classList.remove("modal--active");
    setTimeout(() => {
      modal.style.display = "none";
      resetForm();
    }, 200);
  }

  function resetForm() {
    form.reset();
    entryIdField.value = "";
    customSetField.style.display = "none";
    imagePreview.style.display = "none";
    imagePreviewImg.src = "";
    modalSubmit.disabled = false;
    modalSubmit.textContent = "Save Entry";
  }

  // Open for add
  if (addBtn) {
    addBtn.addEventListener("click", () => {
      resetForm();
      imageField.required = true;
      openModal("Add Entry");
    });
  }

  // Close handlers
  modalClose.addEventListener("click", closeModal);
  modalCancel.addEventListener("click", closeModal);
  modalBackdrop.addEventListener("click", closeModal);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.classList.contains("modal--active")) {
      closeModal();
    }
  });

  // "Other" set conditional input
  setField.addEventListener("change", () => {
    if (setField.value === "other") {
      customSetField.style.display = "block";
      customSetInput.required = true;
    } else {
      customSetField.style.display = "none";
      customSetInput.required = false;
      customSetInput.value = "";
    }
  });

  // Image preview
  imageField.addEventListener("change", () => {
    const file = imageField.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        imagePreviewImg.src = e.target.result;
        imagePreview.style.display = "block";
      };
      reader.readAsDataURL(file);
    } else {
      imagePreview.style.display = "none";
      imagePreviewImg.src = "";
    }
  });

  // --- Submit (Create / Update) ---

  modalSubmit.addEventListener("click", async () => {
    // Basic validation
    if (!nameField.value.trim()) {
      alert("Curio name is required.");
      return;
    }
    if (numberPulledField.value === "" || parseInt(numberPulledField.value) < 0) {
      alert("Number pulled must be a non-negative number.");
      return;
    }
    if (!descriptionField.value.trim()) {
      alert("Description is required.");
      return;
    }

    const isEdit = !!entryIdField.value;

    // For new entries, image is required
    if (!isEdit && (!imageField.files || !imageField.files[0])) {
      alert("An image is required for new entries.");
      return;
    }

    modalSubmit.disabled = true;
    modalSubmit.textContent = "Saving...";

    try {
      let setId = setField.value;

      // Handle custom set creation
      if (setId === "other") {
        const customName = customSetInput.value.trim();
        if (!customName) {
          alert("Please enter a custom set name.");
          modalSubmit.disabled = false;
          modalSubmit.textContent = "Save Entry";
          return;
        }

        const setResp = await fetch("/api/curios/sets", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: customName }),
        });

        if (!setResp.ok) {
          const err = await setResp.json();
          alert(err.error || "Failed to create set.");
          modalSubmit.disabled = false;
          modalSubmit.textContent = "Save Entry";
          return;
        }

        const newSet = await setResp.json();
        setId = newSet.id;
      }

      // Build form data
      const formData = new FormData();
      formData.append("name", nameField.value.trim());
      formData.append("number_pulled", numberPulledField.value);
      formData.append("description", descriptionField.value.trim());
      formData.append("set_id", setId);

      if (imageField.files && imageField.files[0]) {
        formData.append("image", imageField.files[0]);
      }

      const url = isEdit ? `/api/curios/${entryIdField.value}` : "/api/curios/";
      const method = isEdit ? "PUT" : "POST";

      const resp = await fetch(url, { method, body: formData });

      if (!resp.ok) {
        const err = await resp.json();
        alert(err.error || "Failed to save entry.");
        modalSubmit.disabled = false;
        modalSubmit.textContent = "Save Entry";
        return;
      }

      // Success — reload page to show updated data
      window.location.reload();
    } catch (err) {
      alert("An error occurred. Please try again.");
      console.error(err);
      modalSubmit.disabled = false;
      modalSubmit.textContent = "Save Entry";
    }
  });

  // --- Edit Entry ---

  document.querySelectorAll(".curio-entry__edit-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      resetForm();

      entryIdField.value = btn.getAttribute("data-id");
      nameField.value = btn.getAttribute("data-name");
      numberPulledField.value = btn.getAttribute("data-number-pulled");
      descriptionField.value = btn.getAttribute("data-description");
      setField.value = btn.getAttribute("data-set-id");
      imageField.required = false; // Image optional for edits

      // Show current image as preview
      const filename = btn.getAttribute("data-image-filename");
      if (filename) {
        imagePreviewImg.src = `/static/uploads/curios/${filename}`;
        imagePreview.style.display = "block";
      }

      openModal("Edit Entry");
    });
  });

  // --- Delete Entry ---

  document.querySelectorAll(".curio-entry__delete-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Are you sure you want to delete this entry?")) return;

      const id = btn.getAttribute("data-id");
      try {
        const resp = await fetch(`/api/curios/${id}`, { method: "DELETE" });
        if (!resp.ok) {
          const err = await resp.json();
          alert(err.error || "Failed to delete entry.");
          return;
        }
        window.location.reload();
      } catch (err) {
        alert("An error occurred. Please try again.");
        console.error(err);
      }
    });
  });
})();
