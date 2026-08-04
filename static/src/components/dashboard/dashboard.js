/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class ISPBillingDashboard extends Component {
    static template = "isp_billing_automation.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");

        this.interfaceHistory = {}; // Stores rolling 15-point traffic history per interface

        this.state = useState({
            loading: true,
            cronRunning: false,
            chartToggles: {}, // Map of interface key -> boolean (true to show chart)
            data: {
                total_subscribers: 0,
                active_subscribers: 0,
                isolated_subscribers: 0,
                mrr: 0,
                total_unpaid_amount: 0,
                unpaid_count: 0,
                total_routers: 0,
                connected_routers: 0,
                traffic_interfaces: [],
                subscriber_traffics: [],
                recent_logs: [],
            }
        });

        this.refreshInterval = null;

        onWillStart(async () => {
            await this.loadDashboardData();
            // Fast Auto Refresh traffic like Winbox (every 3 seconds)
            this.refreshInterval = setInterval(() => {
                this.loadDashboardData(true);
            }, 3000);
        });

        onWillUnmount(() => {
            if (this.refreshInterval) {
                clearInterval(this.refreshInterval);
            }
        });
    }

    async loadDashboardData(silent = false) {
        if (!silent) {
            this.state.loading = true;
        }
        try {
            const res = await this.orm.call(
                "isp.dashboard.service",
                "get_dashboard_data",
                []
            );
            if (res) {
                this.state.data = {
                    total_subscribers: res.total_subscribers || 0,
                    active_subscribers: res.active_subscribers || 0,
                    isolated_subscribers: res.isolated_subscribers || 0,
                    mrr: res.mrr || 0,
                    total_unpaid_amount: res.total_unpaid_amount || 0,
                    unpaid_count: res.unpaid_count || 0,
                    total_routers: res.total_routers || 0,
                    connected_routers: res.connected_routers || 0,
                    traffic_interfaces: res.traffic_interfaces || [],
                    subscriber_traffics: res.subscriber_traffics || [],
                    recent_logs: res.recent_logs || [],
                };

                // Update rolling interface history
                (res.traffic_interfaces || []).forEach(iface => {
                    const key = iface.router_name + '_' + iface.name;
                    if (!this.interfaceHistory[key]) {
                        this.interfaceHistory[key] = [];
                    }
                    this.interfaceHistory[key].push({
                        rx: iface.rx_bps || 0,
                        tx: iface.tx_bps || 0,
                        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                    });
                    if (this.interfaceHistory[key].length > 15) {
                        this.interfaceHistory[key].shift();
                    }
                });
            }
        } catch (error) {
            console.error("Failed to load ISP Dashboard Data", error);
        } finally {
            this.state.loading = false;
        }
    }

    toggleInterfaceChart(ifaceKey) {
        this.state.chartToggles[ifaceKey] = !this.state.chartToggles[ifaceKey];
    }

    isChartEnabled(ifaceKey) {
        return !!this.state.chartToggles[ifaceKey];
    }

    getChartMeta(ifaceKey) {
        const history = this.interfaceHistory[ifaceKey] || [];
        if (history.length === 0) {
            return {
                peakFormatted: "0 bps",
                startTime: "-",
                endTime: "-",
                rxPoints: "0,35 220,35",
                txPoints: "0,35 220,35"
            };
        }

        const rxVals = history.map(h => h.rx);
        const txVals = history.map(h => h.tx);
        const allVals = [...rxVals, ...txVals];
        const maxVal = Math.max(...allVals, 1000);
        
        const width = 220;
        const height = 45;

        const getPoints = (vals) => {
            if (vals.length === 1) return `0,${height / 2} ${width},${height / 2}`;
            return vals.map((val, idx) => {
                const x = (idx / (vals.length - 1)) * width;
                const y = (height - 5) - ((val / maxVal) * (height - 10));
                return `${x.toFixed(1)},${y.toFixed(1)}`;
            }).join(" ");
        };

        return {
            peakFormatted: this.formatSpeed(maxVal),
            startTime: history[0].time,
            endTime: history[history.length - 1].time,
            rxPoints: getPoints(rxVals),
            txPoints: getPoints(txVals)
        };
    }

    formatIDR(val) {
        return new Intl.NumberFormat('id-ID', {
            style: 'currency',
            currency: 'IDR',
            maximumFractionDigits: 0
        }).format(val || 0);
    }

    formatSpeed(bps) {
        if (!bps || bps <= 0) return "0 bps";
        if (bps >= 1000000) {
            return (bps / 1000000).toFixed(2) + " Mbps";
        } else if (bps >= 1000) {
            return (bps / 1000).toFixed(1) + " Kbps";
        }
        return bps + " bps";
    }

    formatBytes(bytes) {
        if (!bytes || bytes <= 0) return "0 B";
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    async onTriggerCron() {
        this.state.cronRunning = true;
        try {
            await this.orm.call(
                "isp.dashboard.service",
                "trigger_cron_manual",
                []
            );
            this.notification.add(
                "Proses Cron Penagihan H-3 & Isolir H+15 berhasil dijalankan!",
                { title: "Sukses", type: "success" }
            );
            await this.loadDashboardData(true);
        } catch (error) {
            this.notification.add(
                "Gagal menjalankan Cron Job: " + error.message,
                { title: "Error", type: "danger" }
            );
        } finally {
            this.state.cronRunning = false;
        }
    }

    openSubscribers() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'ISP Subscribers',
            res_model: 'res.partner',
            domain: [['is_isp_subscriber', '=', true]],
            views: [[false, 'tree'], [false, 'form']],
        });
    }

    openIsolatedSubscribers() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Pelanggan Terisolir',
            res_model: 'res.partner',
            domain: [['is_isp_subscriber', '=', true], ['service_status', '=', 'isolated']],
            views: [[false, 'tree'], [false, 'form']],
        });
    }

    openUnpaidInvoices() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Invoice Unpaid (Tunggakan ISP)',
            res_model: 'account.move',
            domain: [
                ['move_type', '=', 'out_invoice'],
                ['state', '=', 'posted'],
                ['payment_state', 'not in', ['paid', 'in_payment', 'reversed']],
                ['is_isp_invoice', '=', true]
            ],
            views: [[false, 'tree'], [false, 'form']],
        });
    }

    openRouters() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'MikroTik Routers',
            res_model: 'isp.mikrotik.router',
            views: [[false, 'tree'], [false, 'form']],
        });
    }

    openLogs() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'System Logs',
            res_model: 'isp.log',
            views: [[false, 'tree'], [false, 'form']],
        });
    }
}

registry.category("actions").add("isp_billing_dashboard", ISPBillingDashboard);
