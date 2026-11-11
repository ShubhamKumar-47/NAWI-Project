/**
 * NAWI Test Report Management System (NTRMS)
 * Enterprise Laboratory Information Management Frontend Controller
 */

(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    initSidebarToggle();
    initLiveTableSearch();
    initFormLoadingSpinners();
    initPasswordToggles();
    initDemoLoginFiller();
    initTooltips();
  });

  /**
   * 1. Responsive Sidebar Toggle for Desktop and Mobile/Tablet
   */
  function initSidebarToggle() {
    const sidebar = document.getElementById("sidebar");
    const sidebarToggle = document.getElementById("sidebarToggle");
    const sidebarBackdrop = document.getElementById("sidebarBackdrop");
    const pageWrapper = document.getElementById("page-content-wrapper");

    if (!sidebar || !sidebarToggle) return;

    function toggleSidebar(e) {
      if (e) e.preventDefault();
      const isMobile = window.innerWidth < 992;
      if (isMobile) {
        sidebar.classList.toggle("show");
        if (sidebarBackdrop) {
          sidebarBackdrop.classList.toggle("show");
        }
      } else {
        document.body.classList.toggle("sidebar-collapsed");
        if (pageWrapper) {
          pageWrapper.classList.toggle("sidebar-collapsed");
        }
      }
    }

    sidebarToggle.addEventListener("click", toggleSidebar);

    if (sidebarBackdrop) {
      sidebarBackdrop.addEventListener("click", function () {
        sidebar.classList.remove("show");
        sidebarBackdrop.classList.remove("show");
      });
    }

    // Close mobile sidebar on window resize to desktop
    window.addEventListener("resize", function () {
      if (window.innerWidth >= 992 && sidebar.classList.contains("show")) {
        sidebar.classList.remove("show");
        if (sidebarBackdrop) sidebarBackdrop.classList.remove("show");
      }
    });
  }

  /**
   * 2. Live Searchable Tables
   * Attach [data-table-search] to an input to filter rows in the target table [data-searchable-table]
   */
  function initLiveTableSearch() {
    const searchInputs = document.querySelectorAll("[data-table-search]");
    searchInputs.forEach(function (input) {
      const targetSelector = input.getAttribute("data-table-search");
      const targetTable = document.querySelector(targetSelector);
      if (!targetTable) return;

      const tbody = targetTable.querySelector("tbody");
      if (!tbody) return;

      input.addEventListener("input", function () {
        const query = input.value.trim().toLowerCase();
        const rows = tbody.querySelectorAll("tr:not(.no-search)");
        let visibleCount = 0;

        rows.forEach(function (row) {
          // If the row is an empty state placeholder, skip
          if (row.classList.contains("empty-state-row")) return;

          const text = row.textContent.toLowerCase();
          if (!query || text.indexOf(query) !== -1) {
            row.style.display = "";
            visibleCount++;
          } else {
            row.style.display = "none";
          }
        });

        // Manage dynamic "No matching records found" message
        let noMatchRow = tbody.querySelector(".no-match-row");
        if (visibleCount === 0 && query !== "") {
          if (!noMatchRow) {
            const colCount = targetTable.querySelectorAll("thead th").length || 6;
            noMatchRow = document.createElement("tr");
            noMatchRow.className = "no-match-row";
            noMatchRow.innerHTML = `
              <td colspan="${colCount}" class="text-center py-4 text-muted">
                <i class="bi bi-search text-secondary d-block fs-3 mb-2"></i>
                <div class="fw-semibold">No matching records found</div>
                <small class="text-muted">No rows match "<strong>${escapeHtml(query)}</strong>". Try adjusting your search term.</small>
              </td>
            `;
            tbody.appendChild(noMatchRow);
          }
          noMatchRow.style.display = "";
        } else if (noMatchRow) {
          noMatchRow.style.display = "none";
        }

        // Optional count indicator
        const countTarget = document.querySelector(input.getAttribute("data-count-target"));
        if (countTarget) {
          countTarget.textContent = visibleCount;
        }
      });
    });
  }

  /**
   * 3. Loading Spinners on Form Submissions
   * Prevents accidental double submissions and provides instant tactile feedback.
   */
  function initFormLoadingSpinners() {
    const forms = document.querySelectorAll("form:not(.no-loading)");
    forms.forEach(function (form) {
      form.addEventListener("submit", function (e) {
        // If form is invalid according to HTML5 validation, don't trigger loading state
        if (!form.checkValidity()) return;

        const submitBtn = form.querySelector('button[type="submit"]:not(.no-spinner)');
        if (submitBtn && !submitBtn.disabled) {
          const originalHtml = submitBtn.innerHTML;
          const loadingText = submitBtn.getAttribute("data-loading-text") || "Processing...";
          submitBtn.disabled = true;
          submitBtn.innerHTML = `
            <span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>
            ${loadingText}
          `;

          // Safety reset after 15 seconds in case of network stall or file download
          setTimeout(function () {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalHtml;
          }, 15000);
        }
      });
    });
  }

  /**
   * 4. Password Visibility Toggles
   */
  function initPasswordToggles() {
    const toggleBtns = document.querySelectorAll(".btn-toggle-password");
    toggleBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        const input = btn.closest(".input-group").querySelector("input");
        const icon = btn.querySelector("i");
        if (!input) return;

        if (input.type === "password") {
          input.type = "text";
          if (icon) {
            icon.classList.remove("bi-eye");
            icon.classList.add("bi-eye-slash");
          }
        } else {
          input.type = "password";
          if (icon) {
            icon.classList.remove("bi-eye-slash");
            icon.classList.add("bi-eye");
          }
        }
      });
    });
  }

  /**
   * 5. Demo Login Auto-fill Helper
   */
  function initDemoLoginFiller() {
    const demoButtons = document.querySelectorAll("[data-demo-email]");
    const emailField = document.getElementById("id_username") || document.getElementById("id_login") || document.querySelector('input[name="login"]');
    const passwordField = document.getElementById("id_password") || document.querySelector('input[name="password"]');

    if (!emailField || !passwordField) return;

    demoButtons.forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        const email = btn.getAttribute("data-demo-email");
        const pass = btn.getAttribute("data-demo-password");
        if (email) emailField.value = email;
        if (pass) passwordField.value = pass;
        emailField.focus();

        // Flash indicator on inputs
        emailField.classList.add("is-valid");
        passwordField.classList.add("is-valid");
        setTimeout(function () {
          emailField.classList.remove("is-valid");
          passwordField.classList.remove("is-valid");
        }, 1500);
      });
    });
  }

  /**
   * 6. Initialize Bootstrap Tooltips
   */
  function initTooltips() {
    if (typeof bootstrap !== "undefined" && bootstrap.Tooltip) {
      const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
      tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
      });
    }
  }

  function escapeHtml(text) {
    const map = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;"
    };
    return text.replace(/[&<>"']/g, function (m) { return map[m]; });
  }

})();

