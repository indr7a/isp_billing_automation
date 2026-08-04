# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class ISPDashboardService(models.AbstractModel):
    _name = 'isp.dashboard.service'
    _description = 'ISP Dashboard Data Service'

    @api.model
    def get_dashboard_data(self):
        """Returns aggregated metrics for the Odoo 17 OWL Dashboard (with Filtered Subscriber Traffic & Interface Stats)"""
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

        # 1. Interface Traffic Stats (Compact)
        traffic_interfaces = []
        # 2. Active Subscriber Traffic Stats (Filtered for Odoo Subscribers & Live Queues)
        subscriber_traffics = []

        for router in routers.filtered(lambda r: r.status == 'connected'):
            try:
                conn, api_conn = router.get_connection()
                if api_conn:
                    # Interface Traffic
                    try:
                        if_resource = api_conn.get_resource('/interface')
                        interfaces = if_resource.get()
                        for item in interfaces[:6]:
                            if_name = item.get('name', '')
                            is_running = item.get('running') == 'true' or item.get('running') == True
                            
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
                                'rx_bytes': rx_byte,
                                'tx_bytes': tx_byte,
                                'rx_bps': rx_bps,
                                'tx_bps': tx_bps,
                            })
                    except Exception as e_if:
                        _logger.warning(f"Could not fetch interfaces: {str(e_if)}")

                    # Simple Queue Subscriber Traffic (With Smart Filtering)
                    try:
                        sq_resource = api_conn.get_resource('/queue/simple')
                        queues = sq_resource.get()
                        for q in queues:
                            q_name = q.get('name', '')
                            q_target = q.get('target', '')
                            clean_ip = q_target.split('/')[0] if q_target else ''
                            is_disabled = q.get('disabled') == 'true' or q.get('disabled') == True
                            
                            rate_str = q.get('rate', '0/0')
                            rate_parts = rate_str.split('/') if '/' in rate_str else ['0', '0']
                            tx_bps = int(rate_parts[0]) if len(rate_parts) > 0 and rate_parts[0].isdigit() else 0
                            rx_bps = int(rate_parts[1]) if len(rate_parts) > 1 and rate_parts[1].isdigit() else 0

                            bytes_str = q.get('bytes', '0/0')
                            bytes_parts = bytes_str.split('/') if '/' in bytes_str else ['0', '0']
                            tx_bytes = int(bytes_parts[0]) if len(bytes_parts) > 0 and bytes_parts[0].isdigit() else 0
                            rx_bytes = int(bytes_parts[1]) if len(bytes_parts) > 1 and bytes_parts[1].isdigit() else 0

                            # Match with registered Odoo Subscribers
                            partner = subscribers.filtered(
                                lambda s: s.simple_queue_name == q_name or s.ip_address == clean_ip or (s.name == q_name and s.is_isp_subscriber)
                            )

                            # FILTER RULE:
                            # Include IF it matches a registered Odoo Subscriber OR IF it has active live traffic (rx_bps > 0 or tx_bps > 0)
                            # Exclude 0-bps orphan queues that do NOT belong to any Odoo subscriber.
                            if not partner and rx_bps == 0 and tx_bps == 0:
                                continue

                            partner_name = partner[0].name if partner else q_name
                            partner_status = partner[0].service_status if partner else ('isolated' if is_disabled else 'active')
                            is_registered = bool(partner)

                            subscriber_traffics.append({
                                'name': partner_name,
                                'queue_name': q_name,
                                'ip_address': clean_ip,
                                'status': partner_status,
                                'is_disabled': is_disabled,
                                'is_registered': is_registered,
                                'rx_bps': rx_bps,
                                'tx_bps': tx_bps,
                                'rx_bytes': rx_bytes,
                                'tx_bytes': tx_bytes,
                            })
                    except Exception as e_sq:
                        _logger.warning(f"Could not fetch simple queue traffic: {str(e_sq)}")

                    conn.disconnect()
            except Exception as e:
                _logger.warning(f"Bypassing traffic stats for router {router.name}: {str(e)}")

        subscriber_traffics.sort(key=lambda x: x['rx_bps'] + x['tx_bps'], reverse=True)

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
            'subscriber_traffics': subscriber_traffics,
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
