/* ISP Billing Mobile PWA Application Logic (Multi-Company & Interactive MikroTik Dashboard Enabled) */

class ISPBillingPWA {
    constructor() {
        this.currentTab = 'home';
        this.currentSubStatus = 'all';
        this.currentInvStatus = 'unpaid';
        this.selectedCompanyId = 'all';
        this.subscribersData = [];
        this.deferredPrompt = null;

        this.init();
    }

    init() {
        document.addEventListener('DOMContentLoaded', () => {
            const compSelect = document.getElementById('pwa-company-select');
            if (compSelect) {
                this.selectedCompanyId = compSelect.value || 'all';
            }
            this.loadDashboardData();
            this.bindEvents();
            this.initPWAInstall();
        });
    }

    bindEvents() {
        // Live search input handler
        const searchInput = document.getElementById('sub-search-input');
        if (searchInput) {
            let debounceTimeout;
            searchInput.addEventListener('input', (e) => {
                clearTimeout(debounceTimeout);
                debounceTimeout = setTimeout(() => {
                    this.loadSubscribers(e.target.value, this.currentSubStatus);
                }, 300);
            });
        }
    }

    // Company Switcher Handler
    changeCompany(companyId) {
        this.selectedCompanyId = companyId;
        this.showToast(`Memuat data untuk perusahaan yang dipilih...`, true);

        // Reload data for all tabs dynamically
        this.loadDashboardData();

        if (this.currentTab === 'subscribers') {
            this.loadSubscribers('', this.currentSubStatus);
        } else if (this.currentTab === 'invoices') {
            this.loadInvoices('', this.currentInvStatus);
        } else if (this.currentTab === 'routers') {
            this.loadRouters();
        }
    }

    // Helper for Odoo JSON-RPC API call
    async jsonRpc(url, params = {}) {
        try {
            params.selected_company_id = this.selectedCompanyId;
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    jsonrpc: "2.0",
                    method: "call",
                    params: params,
                    id: Math.floor(Math.random() * 1000)
                })
            });
            const data = await response.json();
            if (data.error) {
                console.error("RPC Error:", data.error);
                return { success: false, message: data.error.data ? data.error.data.message : 'Error Server' };
            }
            return data.result;
        } catch (err) {
            console.error("Fetch Exception:", err);
            return { success: false, message: 'Koneksi jaringan terputus' };
        }
    }

    // Toast Notification
    showToast(message, isSuccess = true) {
        const toastEl = document.getElementById('pwa-toast');
        const msgEl = document.getElementById('toast-message');
        if (toastEl && msgEl) {
            msgEl.textContent = message;
            toastEl.className = `toast align-items-center text-white border-0 shadow-lg ${isSuccess ? 'bg-teal' : 'bg-danger'}`;
            const toast = new bootstrap.Toast(toastEl, { delay: 3500 });
            toast.show();
        }
    }

    // Switch Bottom Nav Tabs
    switchTab(tabName, subFilter = null) {
        this.currentTab = tabName;

        // Hide all tab panes
        document.querySelectorAll('.tab-pane').forEach(el => el.classList.add('d-none'));
        document.querySelectorAll('.pwa-bottom-nav .nav-item').forEach(el => el.classList.remove('active'));

        // Show active pane & bottom nav
        const activePane = document.getElementById(`tab-${tabName}`);
        const activeNav = document.getElementById(`nav-${tabName}`);
        if (activePane) activePane.classList.remove('d-none');
        if (activeNav) activeNav.classList.add('active');

        // Lazy load data based on tab
        if (tabName === 'home') {
            this.loadDashboardData();
        } else if (tabName === 'subscribers') {
            if (subFilter) this.currentSubStatus = subFilter;
            this.loadSubscribers('', this.currentSubStatus);
        } else if (tabName === 'invoices') {
            this.loadInvoices('', this.currentInvStatus);
        } else if (tabName === 'routers') {
            this.loadRouters();
        }

        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // Load Dashboard Data
    async loadDashboardData() {
        const res = await this.jsonRpc('/isp/pwa/api/dashboard');
        if (res && res.success) {
            if (res.user_name) document.getElementById('user-greeting').textContent = res.user_name;
            document.getElementById('stat-active').textContent = res.active_subscribers;
            document.getElementById('stat-isolated').textContent = res.isolated_subscribers;
            document.getElementById('stat-unpaid').textContent = res.unpaid_count;
            document.getElementById('stat-monthly-revenue').textContent = res.monthly_revenue;

            if (res.current_company_name) {
                const labelEl = document.getElementById('company-revenue-label');
                if (labelEl) labelEl.textContent = `Billing (${res.current_company_name})`;
            }

            // Sync company select dropdown if needed
            const selectEl = document.getElementById('pwa-company-select');
            if (selectEl && res.selected_company_id) {
                selectEl.value = res.selected_company_id;
            }

            // Render Top Download Leaderboard
            const topListEl = document.getElementById('top-download-list');
            if (topListEl) {
                if (res.top_download && res.top_download.length > 0) {
                    topListEl.innerHTML = res.top_download.map((item, idx) => `
                        <div class="list-group-item d-flex justify-content-between align-items-center px-0 py-2 border-0">
                            <div class="d-flex align-items-center gap-2">
                                <span class="badge bg-light text-dark font-11 rounded-circle px-2 py-1">${idx + 1}</span>
                                <div>
                                    <h6 class="mb-0 font-13 fw-semibold text-dark">${item.name}</h6>
                                    <small class="text-muted font-11">${item.queue || item.ip}</small>
                                </div>
                            </div>
                            <span class="badge bg-teal-subtle text-teal font-11 fw-bold">${item.bytes}</span>
                        </div>
                    `).join('');
                } else {
                    topListEl.innerHTML = '<div class="text-center py-3 text-muted font-12">Belum ada statistik trafik data</div>';
                }
            }
        }
    }

    // Load Subscriber List
    async loadSubscribers(query = '', status = 'all') {
        const container = document.getElementById('subscriber-card-list');
        if (!container) return;

        container.innerHTML = '<div class="text-center py-4 text-muted font-12"><i class="fa-solid fa-spinner fa-spin me-2"></i>Memuat pelanggan...</div>';

        const res = await this.jsonRpc('/isp/pwa/api/subscribers', { q: query, status: status });
        if (res && res.success) {
            if (res.subscribers.length === 0) {
                container.innerHTML = '<div class="text-center py-5 text-muted font-13"><i class="fa-solid fa-user-slash fa-2x mb-2 d-block opacity-50"></i>Tidak ada pelanggan ditemukan</div>';
                return;
            }

            container.innerHTML = res.subscribers.map(sub => {
                const isIsolated = sub.service_status === 'isolated';
                const statusBadge = isIsolated ? 
                    '<span class="badge-isolated"><i class="fa-solid fa-ban me-1"></i>TERISOLIR</span>' :
                    (sub.service_status === 'active' ? '<span class="badge-active"><i class="fa-solid fa-circle-check me-1"></i>AKTIF</span>' : '<span class="badge-terminated">PUTUS</span>');

                const actionBtn = isIsolated ?
                    `<button class="btn btn-sm btn-success rounded-pill font-11 px-3 fw-bold" onclick="pwaApp.toggleStatus(${sub.id}, 'active', '${sub.name}')">
                        <i class="fa-solid fa-key me-1"></i> Buka Isolir
                     </button>` :
                    `<button class="btn btn-sm btn-outline-danger rounded-pill font-11 px-3 fw-bold" onclick="pwaApp.toggleStatus(${sub.id}, 'isolated', '${sub.name}')">
                        <i class="fa-solid fa-power-off me-1"></i> Isolir
                     </button>`;

                return `
                    <div class="sub-card shadow-sm">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <div>
                                <h6 class="fw-bold font-14 mb-1 text-dark">${sub.name}</h6>
                                <small class="text-muted font-11 d-block"><i class="fa-solid fa-network-wired me-1"></i> ${sub.ip_address} (${sub.connection_type_label}) • <span class="text-teal">${sub.company_name}</span></small>
                            </div>
                            ${statusBadge}
                        </div>
                        <div class="d-flex justify-content-between align-items-center border-top pt-2 mt-2">
                            <div>
                                <span class="d-block font-11 text-muted">${sub.package_name}</span>
                                <strong class="font-12 text-teal">${sub.monthly_fee}/bln</strong>
                            </div>
                            <div class="d-flex gap-2">
                                <button class="btn btn-sm btn-light text-success rounded-circle icon-circle-sm" title="Kirim WA" onclick="pwaApp.sendWa(${sub.id}, '${sub.name}')">
                                    <i class="fa-brands fa-whatsapp font-15"></i>
                                </button>
                                ${actionBtn}
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        }
    }

    // Filter Subscriber Pills
    filterSubscribers(status) {
        this.currentSubStatus = status;
        document.querySelectorAll('#sub-filter-pills button').forEach(b => {
            if (b.dataset.status === status) {
                b.className = 'btn btn-sm btn-teal rounded-pill font-12 px-3 active';
            } else {
                b.className = 'btn btn-sm btn-outline-secondary rounded-pill font-12 px-3';
            }
        });
        const query = document.getElementById('sub-search-input') ? document.getElementById('sub-search-input').value : '';
        this.loadSubscribers(query, status);
    }

    clearSubSearch() {
        const input = document.getElementById('sub-search-input');
        if (input) {
            input.value = '';
            this.loadSubscribers('', this.currentSubStatus);
        }
    }

    // 1-Click Action: Isolir / Un-isolir
    async toggleStatus(partnerId, targetStatus, partnerName) {
        const actionLabel = targetStatus === 'active' ? 'membuka isolir' : 'MENGISOLIR';
        if (!confirm(`Konfirmasi: Apakah Anda yakin ingin ${actionLabel} layanan internet untuk '${partnerName}'?`)) {
            return;
        }

        const res = await this.jsonRpc('/isp/pwa/api/toggle_status', {
            partner_id: partnerId,
            target_status: targetStatus
        });

        if (res && res.success) {
            this.showToast(res.message, true);
            this.loadSubscribers('', this.currentSubStatus);
            this.loadDashboardData();
        } else {
            this.showToast(res ? res.message : 'Gagal mengeksekusi di MikroTik', false);
        }
    }

    // Load Invoices
    async loadInvoices(query = '', filterState = 'unpaid') {
        const container = document.getElementById('invoice-card-list');
        if (!container) return;

        container.innerHTML = '<div class="text-center py-4 text-muted font-12"><i class="fa-solid fa-spinner fa-spin me-2"></i>Memuat tagihan...</div>';

        const res = await this.jsonRpc('/isp/pwa/api/invoices', { q: query, filter_state: filterState });
        if (res && res.success) {
            if (res.invoices.length === 0) {
                container.innerHTML = '<div class="text-center py-5 text-muted font-13"><i class="fa-solid fa-file-circle-check fa-2x mb-2 d-block opacity-50"></i>Tidak ada tagihan</div>';
                return;
            }

            container.innerHTML = res.invoices.map(inv => {
                const isPaid = inv.payment_state === 'paid' || inv.payment_state === 'in_payment';
                const badgeClass = isPaid ? 'badge-active' : 'badge-isolated';
                const statusText = isPaid ? 'LUNAS' : 'BELUM LUNAS';

                return `
                    <div class="sub-card shadow-sm">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <div>
                                <h6 class="fw-bold font-14 mb-1 text-dark">${inv.partner_name}</h6>
                                <small class="text-muted font-11 d-block"><i class="fa-solid fa-file-invoice me-1"></i> ${inv.name} • <span class="text-teal">${inv.company_name}</span></small>
                            </div>
                            <span class="${badgeClass}">${statusText}</span>
                        </div>
                        <div class="d-flex justify-content-between align-items-center border-top pt-2 mt-2">
                            <div>
                                <small class="d-block font-11 text-muted">Jatuh Tempo: ${inv.invoice_date_due}</small>
                                <strong class="font-14 text-teal">${inv.amount_total}</strong>
                            </div>
                            <div>
                                ${!isPaid ? `
                                    <button class="btn btn-sm btn-outline-success rounded-pill font-11 px-3" onclick="pwaApp.sendWa(${inv.partner_id}, '${inv.partner_name}')">
                                        <i class="fa-brands fa-whatsapp me-1"></i> Pengingat WA
                                    </button>
                                ` : ''}
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        }
    }

    filterInvoices(filterState) {
        this.currentInvStatus = filterState;
        document.getElementById('btn-inv-unpaid').className = filterState === 'unpaid' ? 'btn btn-sm btn-teal rounded-pill font-12 px-3 active' : 'btn btn-sm btn-outline-secondary rounded-pill font-12 px-3';
        document.getElementById('btn-inv-paid').className = filterState === 'paid' ? 'btn btn-sm btn-teal rounded-pill font-12 px-3 active' : 'btn btn-sm btn-outline-secondary rounded-pill font-12 px-3';
        this.loadInvoices('', filterState);
    }

    // Load Interactive MikroTik Router Dashboard Cards
    async loadRouters() {
        const container = document.getElementById('router-card-list');
        if (!container) return;

        container.innerHTML = '<div class="text-center py-4 text-muted font-12"><i class="fa-solid fa-spinner fa-spin me-2"></i>Memuat router MikroTik...</div>';

        const res = await this.jsonRpc('/isp/pwa/api/dashboard');
        if (res && res.success && res.routers) {
            if (res.routers.length === 0) {
                container.innerHTML = '<div class="text-center py-5 text-muted font-13"><i class="fa-solid fa-server fa-2x mb-2 d-block opacity-50"></i>Belum ada Router MikroTik terdaftar</div>';
                return;
            }

            container.innerHTML = res.routers.map(r => `
                <div class="sub-card shadow-sm border-start border-4 ${r.status === 'connected' ? 'border-success' : 'border-danger'}">
                    <div class="d-flex justify-content-between align-items-start mb-2">
                        <div>
                            <h6 class="fw-bold font-15 mb-1 text-dark"><i class="fa-solid fa-server me-2 text-teal"></i> ${r.name}</h6>
                            <small class="text-muted font-11 d-block"><i class="fa-solid fa-globe me-1"></i> ${r.host}:${r.port} • <span class="text-teal fw-bold">${r.company_name}</span></small>
                        </div>
                        <span class="badge ${r.status === 'connected' ? 'bg-success' : 'bg-danger'} font-11 rounded-pill px-2 py-1">${r.status_label}</span>
                    </div>

                    <div class="row text-center bg-light rounded-3 py-2 my-2 g-1">
                        <div class="col-6 border-end">
                            <small class="text-muted font-10 d-block">Total Pelanggan</small>
                            <strong class="font-13 text-dark">${r.subscriber_count} User</strong>
                        </div>
                        <div class="col-6">
                            <small class="text-muted font-10 d-block">Last Sync</small>
                            <strong class="font-11 text-muted">${r.last_sync}</strong>
                        </div>
                    </div>

                    <div class="d-flex justify-content-between align-items-center pt-2">
                        <small class="text-muted font-11"><i class="fa-solid fa-shield-halved me-1"></i> ${r.connection_mode === 'wireguard' ? 'WireGuard Internal' : 'VPN Remote Pihak Ke-3'}</small>
                        <div class="d-flex gap-2">
                            <button class="btn btn-sm btn-outline-primary rounded-pill font-11 px-2 py-1" onclick="pwaApp.testRouter(${r.id}, '${r.name}')" title="Test Koneksi API">
                                <i class="fa-solid fa-wifi me-1"></i> Test Koneksi
                            </button>
                            <button class="btn btn-sm btn-teal rounded-pill font-11 px-2 py-1" onclick="pwaApp.syncRouterQueues(${r.id}, '${r.name}')" title="Sync Simple Queues">
                                <i class="fa-solid fa-rotate me-1"></i> Sync Queues
                            </button>
                        </div>
                    </div>
                </div>
            `).join('');
        }
    }

    // 1-Click Action: Test Connection to Router
    async testRouter(routerId, routerName) {
        this.showToast(`Menguji koneksi ke ${routerName}...`, true);
        const res = await this.jsonRpc('/isp/pwa/api/test_router', { router_id: routerId });
        if (res && res.success) {
            this.showToast(res.message, true);
        } else {
            this.showToast(res ? res.message : 'Gagal terhubung ke Router', false);
        }
        this.loadRouters();
    }

    // 1-Click Action: Sync Simple Queues from Router
    async syncRouterQueues(routerId, routerName) {
        this.showToast(`Menyinkronkan Simple Queue dari ${routerName}...`, true);
        const res = await this.jsonRpc('/isp/pwa/api/sync_router_queues', { router_id: routerId });
        if (res && res.success) {
            this.showToast(res.message, true);
            this.loadDashboardData();
            this.loadRouters();
        } else {
            this.showToast(res ? res.message : 'Gagal menyinkronkan Simple Queue', false);
        }
    }

    // Trigger WA Reminder
    async sendWa(partnerId, partnerName) {
        const res = await this.jsonRpc('/isp/pwa/api/send_wa', { partner_id: partnerId });
        if (res && res.success) {
            this.showToast(res.message, true);
        } else {
            this.showToast(res ? res.message : 'Gagal mengirim WA', false);
        }
    }

    // PWA Install Prompt Listener
    initPWAInstall() {
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            this.deferredPrompt = e;
            const installBtn = document.getElementById('pwa-install-btn');
            if (installBtn) {
                installBtn.classList.remove('d-none');
                installBtn.addEventListener('click', () => {
                    installBtn.classList.add('d-none');
                    this.deferredPrompt.prompt();
                    this.deferredPrompt.userChoice.then((choiceResult) => {
                        this.deferredPrompt = null;
                    });
                });
            }
        });
    }
}

// Instantiate PWA App
const pwaApp = new ISPBillingPWA();
