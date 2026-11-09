
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
// ======================================
// SHELFSENSE BARCODE SCANNER
// ======================================

let shelfScanner = null;
let scannerRunning = false;
let scanLocked = false;

const startButton = document.getElementById("startScanner");
const stopButton = document.getElementById("stopScanner");
const scanMessage = document.getElementById("scanMessage");

function showScanMessage(message, type = "normal") {
    if (!scanMessage) return;

    scanMessage.textContent = message;
    scanMessage.dataset.type = type;
}

async function processBarcode(barcode) {
    if (scanLocked) return;

    scanLocked = true;
    showScanMessage("Processing barcode: " + barcode, "normal");

    try {
        const csrfToken = document.querySelector(
            'meta[name="csrf-token"]'
        )?.content;

        const response = await fetch("/api/scan", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {})
            },
            body: JSON.stringify({ barcode: barcode })
        });

        const result = await response.json();

        if (!response.ok || !result.success) {
            showScanMessage(result.message || "Scan failed.", "error");
            return;
        }

        if (result.low_stock) {
            showScanMessage(
                "RESTOCK ALERT: " + result.product +
                " — only " + result.quantity + " left!",
                "warning"
            );
        } else {
            showScanMessage(
                result.product + " scanned. Remaining stock: " +
                result.quantity,
                "success"
            );
        }

    } catch (error) {
        showScanMessage("Could not contact the server. Try again.", "error");
    } finally {
        setTimeout(() => {
            scanLocked = false;
        }, 1800);
    }
}

async function startShelfScanner() {
    if (scannerRunning) return;

    if (!window.Html5Qrcode) {
        showScanMessage("Scanner library did not load. Refresh the page.", "error");
        return;
    }

    try {
        shelfScanner = new Html5Qrcode("scanner-reader");

        await shelfScanner.start(
            { facingMode: "environment" },
            {
                fps: 10,
                qrbox: { width: 250, height: 150 }
            },
            (decodedText) => {
                processBarcode(decodedText);
            },
            () => {}
        );

        scannerRunning = true;
        showScanMessage("Camera active. Point it at a product barcode.");

    } catch (error) {
        showScanMessage(
            "Could not start camera. Check camera permissions and HTTPS.",
            "error"
        );
    }
}

async function stopShelfScanner() {
    if (!shelfScanner || !scannerRunning) return;

    try {
        await shelfScanner.stop();
        shelfScanner.clear();
        scannerRunning = false;
        showScanMessage("Scanner stopped.");
    } catch (error) {
        showScanMessage("Unable to stop scanner.", "error");
    }
}

if (startButton) {
    startButton.addEventListener("click", startShelfScanner);
}

if (stopButton) {
    stopButton.addEventListener("click", stopShelfScanner);
}
