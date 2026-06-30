// --- API Config ---
const API_BASE = ""; // Relative to server root since backend.py serves the app

// State Store
let shipments = [];
let currentFilter = "all";
let searchQuery = "";

// DOM Elements
const syncBtn = document.getElementById("btn-sync");
const syncIcon = document.getElementById("sync-icon");
const lastSyncTimeText = document.getElementById("last-sync-time");
const searchInput = document.getElementById("search-input");
const filterButtons = document.querySelectorAll(".filter-btn");
const statCards = document.querySelectorAll(".stat-card");
const shipmentsList = document.getElementById("shipments-list");
const loadingSpinner = document.getElementById("loading-spinner");
const emptyMessage = document.getElementById("empty-message");

// Modal Elements
const editModal = document.getElementById("edit-modal");
const modalCloseBtn = document.getElementById("modal-close-btn");
const modalCancelBtn = document.getElementById("modal-cancel-btn");
const editForm = document.getElementById("edit-form");
const editStoreInput = document.getElementById("edit-store");
const editOrderIdInput = document.getElementById("edit-order-id");
const editOriginalTrackingInput = document.getElementById("edit-original-tracking");
const editTrackingInput = document.getElementById("edit-tracking");
const editCarrierInput = document.getElementById("edit-carrier");
const editPhoneInput = document.getElementById("edit-phone");
const editNotesTextarea = document.getElementById("edit-notes");

// --- Initialization ---
document.addEventListener("DOMContentLoaded", () => {
    fetchShipments();
    setupEventListeners();
});

// --- Event Listeners ---
function setupEventListeners() {
    // Sync Button
    syncBtn.addEventListener("click", triggerSync);

    // Search Input
    searchInput.addEventListener("input", (e) => {
        searchQuery = e.target.value.toLowerCase().trim();
        renderShipments();
    });

    // Filter Buttons
    filterButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            filterButtons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            currentFilter = btn.getAttribute("data-filter");
            renderShipments();
        });
    });

    // Stat Cards (Quick Filter)
    statCards.forEach(card => {
        card.addEventListener("click", () => {
            const filter = card.getAttribute("data-filter");
            
            // Highlight matching filter button
            filterButtons.forEach(btn => {
                if (btn.getAttribute("data-filter") === filter) {
                    btn.classList.add("active");
                } else {
                    btn.classList.remove("active");
                }
            });
            
            currentFilter = filter;
            renderShipments();
        });
    });

    // Modal Close
    modalCloseBtn.addEventListener("click", closeModal);
    modalCancelBtn.addEventListener("click", closeModal);
    
    // Close modal on click outside
    window.addEventListener("click", (e) => {
        if (e.target === editModal) closeModal();
    });

    // Edit Form Submit
    editForm.addEventListener("submit", submitEditForm);
}

// --- Fetch Shipments ---
async function fetchShipments() {
    try {
        const response = await fetch(`${API_BASE}/api/shipments`);
        if (response.ok) {
            shipments = await response.json();
            renderShipments();
            updateStats();
        } else {
            console.error("Failed to load shipments database.");
        }
    } catch (e) {
        console.error("Connection error while loading shipments:", e);
    }
}

// --- Trigger Sync ---
async function triggerSync() {
    // UI Loading State
    syncBtn.disabled = true;
    syncIcon.classList.add("spinning");
    syncBtn.querySelector("span").innerText = "Syncing...";
    
    shipmentsList.style.display = "none";
    emptyMessage.style.display = "none";
    loadingSpinner.style.display = "block";

    try {
        const response = await fetch(`${API_BASE}/api/sync`, { method: "POST" });
        if (response.ok) {
            const result = await response.json();
            if (result.success) {
                shipments = result.shipments;
                // Set last sync timestamp
                const now = new Date();
                lastSyncTimeText.innerText = `Last Synced: ${now.toLocaleTimeString()} ${now.toLocaleDateString()}`;
            } else {
                alert(`Sync failed: ${result.error}`);
            }
        } else {
            alert("Server returned error during sync.");
        }
    } catch (e) {
        console.error("Error connecting to server for sync:", e);
        alert("Connection lost. Make sure the backend server is running.");
    } finally {
        // UI Reset
        syncBtn.disabled = false;
        syncIcon.classList.remove("spinning");
        syncBtn.querySelector("span").innerText = "Sync Inboxes";
        
        loadingSpinner.style.display = "none";
        shipmentsList.style.display = "grid";
        
        renderShipments();
        updateStats();
    }
}

// --- Update Stats Header ---
function updateStats() {
    const total = shipments.length;
    const transit = shipments.filter(s => s.status === "In Transit" || s.status === "Info Received" || s.status === "Out for Delivery").length;
    const delivered = shipments.filter(s => s.status === "Delivered").length;
    const pending = total - transit - delivered;

    document.getElementById("stat-total").innerText = total;
    document.getElementById("stat-transit").innerText = transit;
    document.getElementById("stat-delivered").innerText = delivered;
    document.getElementById("stat-pending").innerText = pending;
}

// --- Render Shipments ---
function renderShipments() {
    shipmentsList.innerHTML = "";
    
    // Filter logic
    let filtered = shipments;
    
    if (currentFilter !== "all") {
        if (currentFilter === "In Transit") {
            filtered = shipments.filter(s => s.status === "In Transit" || s.status === "Info Received" || s.status === "Out for Delivery");
        } else if (currentFilter === "Delivered") {
            filtered = shipments.filter(s => s.status === "Delivered");
        } else {
            // Pending/Unknown
            filtered = shipments.filter(s => s.status !== "Delivered" && s.status !== "In Transit" && s.status !== "Info Received" && s.status !== "Out for Delivery");
        }
    }
    
    // Search logic
    if (searchQuery) {
        filtered = filtered.filter(s => 
            (s.order_id && s.order_id.toLowerCase().includes(searchQuery)) ||
            (s.tracking_number && s.tracking_number.toLowerCase().includes(searchQuery)) ||
            (s.store && s.store.toLowerCase().includes(searchQuery)) ||
            (s.carrier && s.carrier.toLowerCase().includes(searchQuery)) ||
            (s.notes && s.notes.toLowerCase().includes(searchQuery)) ||
            (s.subject && s.subject.toLowerCase().includes(searchQuery))
        );
    }

    if (filtered.length === 0) {
        emptyMessage.style.display = "block";
        return;
    }

    emptyMessage.style.display = "none";

    filtered.forEach(item => {
        const card = document.createElement("div");
        
        // Define card status class
        let statusClass = "status-pending";
        if (item.status === "Delivered") statusClass = "status-delivered";
        else if (item.status === "In Transit" || item.status === "Out for Delivery") statusClass = "status-intransit";
        
        card.className = `shipment-card ${statusClass}`;
        
        // Format Store badge
        const storeClean = item.store || "Unknown Store";
        const storeBadgeClass = storeClean.toLowerCase().startsWith("amazon") ? "amazon" : (storeClean.toLowerCase() === "aliexpress" ? "aliexpress" : "unknown");
        
        // Format Tracking / Carrier details
        const trackingNum = item.tracking_number || "No Tracking Num";
        const carrier = item.carrier || "Unknown Carrier";
        const statusDetails = item.details || "Awaiting status updates...";
        const trackingUrl = item.tracking_url || (trackingNum !== "No Tracking Num" 
            ? `https://www.17track.net/en/track?nums=${trackingNum}`
            : "#");

        // Optional metadata
        const phoneHtml = item.phone ? `<span><i class="fa-solid fa-phone"></i> ${item.phone}</span>` : "";
        const notesHtml = item.notes ? `<span><i class="fa-solid fa-note-sticky"></i> ${item.notes}</span>` : "";

        // Status Badge Style
        let statusBadgeText = item.status || "Unknown";
        let statusBadgeType = "pending";
        if (item.status === "Delivered") statusBadgeType = "delivered";
        else if (item.status === "In Transit" || item.status === "Out for Delivery") statusBadgeType = "intransit";

        card.innerHTML = `
            <div>
                <div class="card-header">
                    <span class="store-badge ${storeBadgeClass}">${storeClean}</span>
                    <span class="status-badge ${statusBadgeType}">${statusBadgeText}</span>
                </div>
                <h3 class="order-title">${item.subject || `Order ${item.order_id || 'ID'}`}</h3>
                
                <div class="meta-row">
                    <span>Order: <strong>${item.order_id || 'N/A'}</strong></span>
                    <span class="tracking-pill">
                        <i class="fa-solid fa-hashtag"></i> 
                        <span>${trackingNum}</span>
                        ${trackingNum !== "No Tracking Num" ? `<i class="fa-regular fa-copy copy-btn" title="Copy tracking code"></i>` : ""}
                    </span>
                </div>
                
                <div class="status-details">
                    <div style="font-weight: 600; font-size: 0.8rem; margin-bottom: 0.25rem; color: #fff;">
                        ${carrier}
                    </div>
                    <div>${statusDetails}</div>
                </div>
            </div>

            <div class="card-footer">
                <div class="phone-notes">
                    ${phoneHtml}
                    ${notesHtml}
                </div>
                <div class="action-row">
                    <button class="btn-icon btn-edit" title="Edit details"><i class="fa-solid fa-pen"></i></button>
                    ${trackingUrl !== "#" ? `<a href="${trackingUrl}" target="_blank" class="btn-icon btn-track-link" title="Open tracking page"><i class="fa-solid fa-arrow-up-right-from-square"></i></a>` : ""}
                </div>
            </div>
        `;

        // Register Copy to Clipboard Event
        const copyBtn = card.querySelector(".copy-btn");
        if (copyBtn) {
            copyBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                navigator.clipboard.writeText(trackingNum);
                copyBtn.className = "fa-solid fa-check copy-btn";
                copyBtn.style.color = "var(--accent-green)";
                setTimeout(() => {
                    copyBtn.className = "fa-regular fa-copy copy-btn";
                    copyBtn.style.color = "";
                }, 2000);
            });
        }

        // Register Edit Click Event
        card.querySelector(".btn-edit").addEventListener("click", () => {
            openEditModal(item);
        });

        shipmentsList.appendChild(card);
    });
}

// --- Modal Handlers ---
function openEditModal(item) {
    editStoreInput.value = item.store || "";
    editOrderIdInput.value = item.order_id || "";
    editOriginalTrackingInput.value = item.tracking_number || "";
    editTrackingInput.value = item.tracking_number || "";
    editCarrierInput.value = item.carrier || "";
    editPhoneInput.value = item.phone || "";
    editNotesTextarea.value = item.notes || "";
    
    editModal.classList.add("active");
}

function closeModal() {
    editModal.classList.remove("active");
    editForm.reset();
}

async function submitEditForm(e) {
    e.preventDefault();
    
    const params = {
        store: editStoreInput.value,
        order_id: editOrderIdInput.value,
        original_tracking_number: editOriginalTrackingInput.value,
        tracking_number: editTrackingInput.value,
        carrier: editCarrierInput.value,
        phone: editPhoneInput.value,
        notes: editNotesTextarea.value
    };

    try {
        const response = await fetch(`${API_BASE}/api/update`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(params)
        });

        if (response.ok) {
            closeModal();
            fetchShipments(); // Reload
        } else {
            const err = await response.json();
            alert(`Error saving: ${err.error || 'Server error'}`);
        }
    } catch (e) {
        console.error("Error saving edits:", e);
        alert("Failed to connect to the server to save changes.");
    }
}
