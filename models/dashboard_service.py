# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class ISPDashboardService(models.AbstractModel):
    _name = 'isp.dashboard.service'
    _description = 'ISP Dashboard Data Service'

    @api.model
    def get_dashboard_data(self):
        """Returns aggregated metrics for the Odoo 17 OWL Dashboard (with Non-blocking Traffic Stats)"""
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
        routers = Router.search([('active', '=', True)])
        total_routers = len(routers)
        connected_routers = len(routers.filtered(lambda r: r.status == 'connected'))

        # Interface Traffic Stats (Only poll routers marked as 'connected' to prevent dashboard timeout)
        traffic_interfaces = []
        for router in routers.filtered(lambda r: r.status == 'connected'):
            try:
                conn, api_conn = router.get_connection()
                if api_conn:
                    if_resource = api_conn.get_resource('/interface')
                    interfaces = if_resource.get()
                    
                    for item in interfaces[:6]: # Limit to top 6 interfaces per router
                        if_name = item.get('name', '')
                        is_running = item.get('running') == 'true' or item.get('running') == True
                        is_disabled = item.get('disabled') == 'true' or item.get('disabled') == True
                        
                        rx_byte = int(item.get('rx-byte', 0))
                        tx_byte = int(item.get('tx-byte', 0))

                        rx_bps = 0
                        tx_bps = 0
                        try:
                            traffic_mon = api_conn.get_binary_resource('/').call('interface/monitor-traffic', {
                                'interface': if_name,
                                'once': ''
                            })
                            if traffic_mon and len(traffic_mon) > 0:
                                rx_bps = int(traffic_mon[0].get('rx-bits-per-second', 0))
                                tx_bps = int(traffic_mon[0].get('tx-bits-per-second', 0))
                        except Exception:
                            pass

                        traffic_interfaces.append({
                            'router_name': router.name,
                            'name': if_name,
                            'type': item.get('type', 'ether'),
                            'running': is_running,
                            'disabled': is_disabled,
                            'rx_bytes': rx_byte,
                            'tx_bytes': tx_byte,
                            'rx_bps': rx_bps,
                            'tx_bps': tx_bps,
                            'rx_mbps': round(rx_bps / 1000000.0, 2),
                            'tx_mbps': round(tx_bps / 1000000.0, 2),
                        })
                    conn.disconnect()
            except Exception as e:
                _logger.warning(f"Bypassing traffic stats for router {router.name}: {str(e)}")

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
            'traffic_interfaces': traffic_interfaces,
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
