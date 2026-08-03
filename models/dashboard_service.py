# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ISPDashboardService(models.AbstractModel):
    _name = 'isp.dashboard.service'
    _description = 'ISP Dashboard Data Service'

    @api.model
    def get_dashboard_data(self):
        """Returns aggregated metrics for the Odoo 17 OWL Dashboard"""
        Partner = self.env['res.partner']
        Move = self.env['account.move']
        Router = self.env['isp.mikrotik.router']
        Log = self.env['isp.log']

        # Subscribers metrics
        subscribers = Partner.search([('is_isp_subscriber', '=', True)])
        total_subscribers = len(subscribers)
        active_subscribers = len(subscribers.filtered(lambda s: s.service_status == 'active'))
        isolated_subscribers = len(subscribers.filtered(lambda s: s.service_status == 'isolated'))

        # Revenue MRR
        mrr = sum(subscribers.filtered(lambda s: s.service_status == 'active').mapped('monthly_fee'))

        # Invoices metrics
        unpaid_invoices = Move.search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'not in', ['paid', 'in_payment', 'reversed']),
            ('is_isp_invoice', '=', True)
        ])
        total_unpaid_amount = sum(unpaid_invoices.mapped('amount_residual'))
        unpaid_count = len(unpaid_invoices)

        # Routers metrics
        routers = Router.search([])
        total_routers = len(routers)
        connected_routers = len(routers.filtered(lambda r: r.status == 'connected'))

        # Aging AR
        aging_ar = Move.get_aging_ar_summary()

        # Recent Logs (latest 5)
        recent_logs_records = Log.search([], limit=5, order='timestamp desc, id desc')
        recent_logs = [{
            'id': log.id,
            'timestamp': fields.Datetime.to_string(log.timestamp),
            'source': log.source,
            'level': log.level,
            'message': log.message,
        } for log in recent_logs_records]

        return {
            'total_subscribers': total_subscribers,
            'active_subscribers': active_subscribers,
            'isolated_subscribers': isolated_subscribers,
            'mrr': mrr,
            'total_unpaid_amount': total_unpaid_amount,
            'unpaid_count': unpaid_count,
            'total_routers': total_routers,
            'connected_routers': connected_routers,
            'aging_ar': aging_ar,
            'recent_logs': recent_logs,
        }

    @api.model
    def trigger_cron_manual(self):
        """Manually triggers the ISP billing & isolation cron job"""
        self.env['account.move']._cron_isp_billing_process()
        self.env['isp.log'].create({
            'source': 'system',
            'level': 'info',
            'message': 'Pengecekan Billing & Isolir Otomatis dijalankan secara manual dari Dashboard',
            'details': 'Manual trigger via OWL Dashboard Action Button'
        })
        return True
