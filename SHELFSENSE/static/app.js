
document.addEventListener("DOMContentLoaded", () => {

    const modal = document.getElementById("productModal");

    const openers = document.querySelectorAll("[data-open-modal]");
    const closers = document.querySelectorAll("[data-close-modal]");

    if (modal) {

        openers.forEach(button => {
            button.addEventListener("click", () => {
                modal.classList.add("open");
                modal.setAttribute("aria-hidden", "false");
            });
        });

        closers.forEach(button => {
            button.addEventListener("click", () => {
                modal.classList.remove("open");
                modal.setAttribute("aria-hidden", "true");
            });
        });

        modal.addEventListener("click", event => {
            if (event.target === modal) {
                modal.classList.remove("open");
                modal.setAttribute("aria-hidden", "true");
            }
        });

        document.addEventListener("keydown", event => {
            if (event.key === "Escape") {
                modal.classList.remove("open");
                modal.setAttribute("aria-hidden", "true");
            }
        });
    }


    // SEARCH AND FILTER

    const search = document.getElementById("searchInput");
    const filter = document.getElementById("statusFilter");

    const rows = document.querySelectorAll("#productRows tr[data-status]");

    function filterRows() {

        const term = (search?.value || "").toLowerCase().trim();
        const status = filter?.value || "all";

        rows.forEach(row => {

            const matchesText = (row.dataset.search || "").includes(term);

            const matchesStatus =
                status === "all" || row.dataset.status === status;

            row.style.display =
                matchesText && matchesStatus ? "" : "none";
        });
    }

    search?.addEventListener("input", filterRows);
    filter?.addEventListener("change", filterRows);


    // FLASH MESSAGE

    document.querySelectorAll(".flash").forEach(message => {

        setTimeout(() => {

            message.style.transition = "opacity .35s";
            message.style.opacity = "0";

            setTimeout(() => message.remove(), 400);

        }, 5000);

    });


    // DEFAULT STOCK DATE

    const stocked = document.querySelector('input[name="stocked_on"]');

    if (stocked && !stocked.value) {

        const today = new Date();
        const localDate = new Date(
            today.getTime() - today.getTimezoneOffset() * 60000
        ).toISOString().slice(0, 10);

        stocked.value = localDate;
    }

});
