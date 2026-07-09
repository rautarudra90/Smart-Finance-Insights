//
// Smart Finance Insights - Frontend Script
//

document.addEventListener("DOMContentLoaded", function () {

    console.log("Smart Finance Insights JS Loaded");

    // -----------------------------
    // SIMPLE FORM VALIDATION (GLOBAL)
    // -----------------------------

    function showAlert(message, type = "success") {
        const alertBox = document.createElement("div");

        alertBox.className = `alert alert-${type} position-fixed top-0 end-0 m-3 shadow`;
        alertBox.style.zIndex = 9999;
        alertBox.innerText = message;

        document.body.appendChild(alertBox);

        setTimeout(() => {
            alertBox.remove();
        }, 3000);
    }

    // -----------------------------
    // INCOME FORM HANDLER
    // -----------------------------

    const incomeForm = document.querySelector("form");

    if (incomeForm && window.location.pathname.includes("income")) {
        incomeForm.addEventListener("submit", function (e) {
            e.preventDefault();

            showAlert("Income added successfully!", "success");
            incomeForm.reset();
        });
    }

    // -----------------------------
    // EXPENSE FORM HANDLER
    // -----------------------------

    if (incomeForm && window.location.pathname.includes("expense")) {
        incomeForm.addEventListener("submit", function (e) {
            e.preventDefault();

            showAlert("Expense added successfully!", "danger");
            incomeForm.reset();
        });
    }

    // -----------------------------
    // BUDGET FORM HANDLER
    // -----------------------------

    if (incomeForm && window.location.pathname.includes("budget")) {
        incomeForm.addEventListener("submit", function (e) {
            e.preventDefault();

            showAlert("Budget saved successfully!", "primary");
            incomeForm.reset();
        });
    }

    // -----------------------------
    // AI INSIGHTS BUTTON
    // -----------------------------

    const aiButton = document.querySelector(".btn.btn-primary");

    if (aiButton && window.location.pathname.includes("ai-insights")) {
        aiButton.addEventListener("click", function () {
            showAlert("AI is analyzing your finances...", "info");
        });
    }

    // -----------------------------
    // SETTINGS TOGGLE FEEDBACK
    // -----------------------------

    const toggles = document.querySelectorAll(".form-check-input");

    toggles.forEach(toggle => {
        toggle.addEventListener("change", function () {
            showAlert("Settings updated", "success");
        });
    });

});