/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class ISPBillingDashboard extends Component {
    static template = "isp_billing_automation.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");

        this.state = useState({
            loading: true,
            cronRunning: false,
            data: {
                total_subscribers: 0,
                active_subscribers: 0,
                isolated_subscribers: 0,
                mrr: 0,
                total_unpaid_amount: 0,
                unpaid_count: 0,
                total_routers: 0,
                connected_routers: 0,
                aging_ar: {},
                recent_logs: [],
            }
        });

        onWillStart(async () => {
            await this.loadDashboardData();
        });
    }

    async loadDashboardData() {
        this.state.loading = true;
        try {
            const res = await this.orm.call(
                "isp.dashboard.service",
                "get_dashboard_data",
                []
            );
            this.state.data = res;
        } catch (error) {
            console.error("Failed to load ISP Dashboard Data", error);
        } finally {
            this.state.loading = false;
        }
    }

    formatIDR(val) {
        return new Intl.NumberFormat('id-ID', {
            style: 'currency',
            currency: 'IDR',
            maximumFractionDigits: 0
        }).format(val || 0);
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
            await this.loadDashboardData();
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
