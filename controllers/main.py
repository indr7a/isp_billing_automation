# -*- coding: utf-8 -*-
from odoo import http, fields, _
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)


class ISPBillingPWAController(http.Controller):

    @http.route('/isp/pwa', type='http', auth='user', website=False)
    def pwa_index(self, **kw):
        """Renders the Mobile PWA App Shell with Multi-Company support"""
        user = request.env.user
        allowed_companies = request.env['res.company'].sudo().search([])
        return request.render('isp_billing_automation.pwa_template', {
            'user': user,
            'company': request.env.company,
            'allowed_companies': allowed_companies,
        })

    @http.route('/isp/pwa/manifest.json', type='http', auth='public', cors='*')
    def pwa_manifest(self, **kw):
        """Serves the PWA Web App Manifest"""
        manifest = {
            "name": "ISP Billing Mobile",
            "short_name": "ISPBilling",
            "start_url": "/isp/pwa",
            "display": "standalone",
            "background_color": "#0f172a",
            "theme_color": "#0d9488",
            "orientation": "portrait",
            "icons": [
                {
                    "src": "/isp/pwa/icon.svg",
                    "sizes": "192x192 512x512",
                    "type": "image/svg+xml",
                    "purpose": "any maskable"
                }
            ]
        }
        return request.make_response(
            json.dumps(manifest),
            headers=[('Content-Type', 'application/json;charset=utf-8')]
        )

    @http.route(['/isp_billing_automation/static/src/img/icon-192.png', '/isp_billing_automation/static/src/img/icon-512.png', '/isp/pwa/icon.svg', '/isp/pwa/icon.png'], type='http', auth='public', cors='*')
    def pwa_icon(self, **kw):
        """Serves dynamic PWA App SVG Icon"""
        svg_code = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
            <rect width="512" height="512" rx="100" fill="#0d9488"/>
            <path d="M256 160c-61.9 0-117.8 24.3-159.2 64l33.9 33.9c32.7-31.3 76.9-50.5 125.3-50.5s92.6 19.2 125.3 50.5l33.9-33.9C373.8 184.3 317.9 160 256 160zm0 96c-35.3 0-67.2 13.9-90.8 36.6l33.9 33.9c14.7-14.2 34.6-22.9 56.9-22.9s42.2 8.7 56.9 22.9l33.9-33.9C323.2 269.9 291.3 256 256 256zm0 96c-13.3 0-24 10.7-24 24s10.7 24 24 24 24-10.7 24-24-10.7-24-24-24z" fill="#ffffff"/>
        </svg>"""
        return request.make_response(
            svg_code,
            headers=[('Content-Type', 'image/svg+xml')]
        )

    @http.route('/isp/pwa/sw.js', type='http', auth='public', cors='*')
    def pwa_service_worker(self, **kw):
        """Serves the PWA Service Worker script"""
        sw_code = """
        const CACHE_NAME = 'isp-billing-pwa-v1';
        const urlsToCache = [
            '/isp/pwa',
            '/isp_billing_automation/static/src/pwa/pwa_style.css',
            '/isp_billing_automation/static/src/pwa/pwa_app.js'
        ];

        self.addEventListener('install', event => {
            event.waitUntil(
                caches.open(CACHE_NAME).then(cache => {
                    return cache.addAll(urlsToCache);
                })
            );
        });

        self.addEventListener('fetch', event => {
            event.respondWith(
                caches.match(event.request).then(response => {
                    return response || fetch(event.request);
                })
            );
        });
        """
        return request.make_response(
            sw_code,
            headers=[('Content-Type', 'application/javascript;charset=utf-8')]
        )

    def _get_target_company_ids(self, selected_company_id=None):
        """Helper to get list of target company IDs based on selection"""
        all_companies = request.env['res.company'].sudo().search([])
        all_comp_ids = all_companies.ids

        if selected_company_id and str(selected_company_id).lower() != 'all':
            try:
                comp_id = int(selected_company_id)
                if comp_id in all_comp_ids:
                    return [comp_id], False
            except (ValueError, TypeError):
                pass

        return all_comp_ids, True

    def _get_partner_company_domain(self, selected_company_id=None):
        comp_ids, is_all = self._get_target_company_ids(selected_company_id)
        if is_all:
            return ['|', '|', ('company_id', '=', False), ('company_id', 'in', comp_ids), ('mikrotik_id.company_id', 'in', comp_ids)]
        else:
            return ['|', ('company_id', 'in', comp_ids), ('mikrotik_id.company_id', 'in', comp_ids)]

    def _get_invoice_company_domain(self, selected_company_id=None):
        comp_ids, is_all = self._get_target_company_ids(selected_company_id)
        if is_all:
            return ['|', ('company_id', '=', False), ('company_id', 'in', comp_ids)]
        else:
            return [('company_id', 'in', comp_ids)]

    def _get_router_company_domain(self, selected_company_id=None):
        comp_ids, is_all = self._get_target_company_ids(selected_company_id)
        if is_all:
            return ['|', ('company_id', '=', False), ('company_id', 'in', comp_ids)]
        else:
            return [('company_id', 'in', comp_ids)]

    def _format_bytes(self, size_bytes):
        if not size_bytes or size_bytes <= 0:
            return "0 B"
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        i = 0
        b = float(size_bytes)
        while b >= 1024 and i < len(units) - 1:
            b /= 1024.0
            i += 1
        return f"{b:.1f} {units[i]}"

    def _format_bps(self, bits_per_sec):
        if not bits_per_sec or bits_per_sec <= 0:
            return "0 bps"
        if bits_per_sec >= 1000000:
            return f"{bits_per_sec / 1000000.0:.1f} Mbps"
        elif bits_per_sec >= 1000:
            return f"{bits_per_sec / 1000.0:.1f} Kbps"
        return f"{bits_per_sec} bps"

    @http.route('/isp/pwa/api/dashboard', type='json', auth='user')
    def get_dashboard_data(self, selected_company_id=None):
        """JSON API returning real-time metrics for mobile dashboard with Multi-Company support"""
        Partner = request.env['res.partner'].sudo()
        Invoice = request.env['account.move'].sudo()
        Router = request.env['isp.mikrotik.router'].sudo()

        partner_domain = self._get_partner_company_domain(selected_company_id)
        invoice_domain = self._get_invoice_company_domain(selected_company_id)
        router_domain = self._get_router_company_domain(selected_company_id)

        # Subscribers count
        domain_sub = [('is_isp_subscriber', '=', True)] + partner_domain
        total_subscribers = Partner.search_count(domain_sub)
        active_subscribers = Partner.search_count(domain_sub + [('service_status', '=', 'active')])
        isolated_subscribers = Partner.search_count(domain_sub + [('service_status', '=', 'isolated')])
        terminated_subscribers = Partner.search_count(domain_sub + [('service_status', '=', 'terminated')])

        # Monthly Revenue & Unpaid
        today = fields.Date.today()
        first_day_month = today.replace(day=1)
        domain_inv_month = [
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', first_day_month)
        ] + invoice_domain

        monthly_invoices = Invoice.search(domain_inv_month)
        monthly_revenue = sum(monthly_invoices.mapped('amount_total'))

        unpaid_invoices = Invoice.search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'not in', ['paid', 'in_payment'])
        ] + invoice_domain)

        total_unpaid_amount = sum(unpaid_invoices.mapped('amount_residual'))
        unpaid_count = len(unpaid_invoices)

        # Router statuses & per-router subscriber count
        routers = Router.search(router_domain)
        router_data = []
        for r in routers:
            sub_count = Partner.search_count([('is_isp_subscriber', '=', True), ('mikrotik_id', '=', r.id)])
            router_data.append({
                'id': r.id,
                'name': r.name,
                'company_name': r.company_id.name if r.company_id else 'Semua Company',
                'connection_mode': r.connection_mode,
                'host': r.host,
                'port': r.port,
                'status': r.status,
                'status_label': 'Connected' if r.status == 'connected' else ('Error' if r.status == 'error' else 'Draft'),
                'subscriber_count': sub_count,
                'last_sync': r.last_sync.strftime('%d-%m-%Y %H:%M') if r.last_sync else '-'
            })

        # Real-Time Interface Traffic & Simple Queue Bandwidth
        traffic_interfaces = []
        top_download_list = []
        try:
            target_comp_ids, _ = self._get_target_company_ids(selected_company_id)
            dashboard_service = request.env['isp.dashboard.service'].sudo().with_context(allowed_company_ids=target_comp_ids)
            summary = dashboard_service.get_dashboard_data()

            # 1. Interfaces traffic
            raw_interfaces = summary.get('traffic_interfaces', [])
            for iface in raw_interfaces[:6]:
                rx_bps = iface.get('rx_bps', 0)
                tx_bps = iface.get('tx_bps', 0)
                rx_bytes = iface.get('rx_bytes', 0)
                tx_bytes = iface.get('tx_bytes', 0)

                traffic_interfaces.append({
                    'router_name': iface.get('router_name', 'Router'),
                    'name': iface.get('name', 'ether1'),
                    'running': iface.get('running', True),
                    'rx_speed': self._format_bps(rx_bps),
                    'tx_speed': self._format_bps(tx_bps),
                    'rx_total': self._format_bytes(rx_bytes),
                    'tx_total': self._format_bytes(tx_bytes),
                })

            # 2. Simple Queue Bandwidth Leaderboard
            raw_top = summary.get('top_download', [])[:5]
            for item in raw_top:
                rx_b = item.get('rx_bytes', 0)
                tx_b = item.get('tx_bytes', 0)
                rx_speed = item.get('rx_bps', 0)
                tx_speed = item.get('tx_bps', 0)

                speed_str = f"↓ {self._format_bps(rx_speed)} / ↑ {self._format_bps(tx_speed)}" if (rx_speed > 0 or tx_speed > 0) else f"{self._format_bytes(rx_b + tx_b)} Total"
                top_download_list.append({
                    'name': item.get('name', 'Subscriber'),
                    'queue': item.get('queue_name') or item.get('ip_address') or '-',
                    'status': item.get('status', 'active'),
                    'bandwidth_str': speed_str,
                    'bytes_str': self._format_bytes(rx_b + tx_b)
                })
        except Exception as e_dash:
            _logger.warning(f"Failed fetching live MikroTik traffic: {str(e_dash)}")

        # Fallback if no queue data from MikroTik yet
        if not top_download_list:
            top_subscribers = Partner.search([('is_isp_subscriber', '=', True)] + partner_domain, limit=5)
            top_download_list = [{
                'name': s.name,
                'queue': s.simple_queue_name or s.ip_address or s.ppp_username or '-',
                'status': s.service_status or 'active',
                'bandwidth_str': "↓ 0 bps / ↑ 0 bps",
                'bytes_str': "0 MB Total"
            } for s in top_subscribers]

        # Companies list for user switcher
        all_comp_recs = request.env['res.company'].sudo().search([])
        user_companies = [{
            'id': c.id,
            'name': c.name
        } for c in all_comp_recs]

        current_company_name = "Semua Perusahaan"
        if selected_company_id and str(selected_company_id).lower() != 'all':
            try:
                comp_rec = request.env['res.company'].sudo().browse(int(selected_company_id))
                if comp_rec.exists():
                    current_company_name = comp_rec.name
            except Exception:
                pass
        elif not selected_company_id:
            current_company_name = request.env.company.name

        return {
            'success': True,
            'user_name': request.env.user.name,
            'current_company_name': current_company_name,
            'selected_company_id': str(selected_company_id) if selected_company_id else 'all',
            'user_companies': user_companies,
            'total_subscribers': total_subscribers,
            'active_subscribers': active_subscribers,
            'isolated_subscribers': isolated_subscribers,
            'terminated_subscribers': terminated_subscribers,
            'monthly_revenue': f"Rp {monthly_revenue:,.0f}".replace(",", "."),
            'total_unpaid_amount': f"Rp {total_unpaid_amount:,.0f}".replace(",", "."),
            'unpaid_count': unpaid_count,
            'routers': router_data,
            'traffic_interfaces': traffic_interfaces,
            'top_download': top_download_list,
        }

    @http.route('/isp/pwa/api/subscribers', type='json', auth='user')
    def get_subscribers(self, q='', status='all', selected_company_id=None):
        """JSON API returning filtered subscriber list with Multi-Company support"""
        Partner = request.env['res.partner'].sudo()
        partner_domain = self._get_partner_company_domain(selected_company_id)

        domain = [('is_isp_subscriber', '=', True)] + partner_domain
        
        if status in ['active', 'isolated', 'terminated']:
            domain.append(('service_status', '=', status))

        if q:
            domain.append('|')
            domain.append('|')
            domain.append(('name', 'ilike', q))
            domain.append(('ip_address', 'ilike', q))
            domain.append(('simple_queue_name', 'ilike', q))

        subscribers = Partner.search(domain, order='name asc', limit=100)
        
        sub_list = []
        for s in subscribers:
            sub_list.append({
                'id': s.id,
                'name': s.name,
                'company_name': s.company_id.name if s.company_id else 'Global',
                'connection_type': s.connection_type,
                'connection_type_label': 'Static IP' if s.connection_type == 'static' else 'PPPoE',
                'ip_address': s.ip_address or s.simple_queue_name or s.ppp_username or '-',
                'mobile': s.mobile or s.phone or '-',
                'service_status': s.service_status or 'active',
                'package_name': s.isp_package_id.name if s.isp_package_id else 'Paket Standar',
                'monthly_fee': f"Rp {s.monthly_fee:,.0f}".replace(",", ".") if s.monthly_fee else 'Rp 0',
                'router_name': s.mikrotik_id.name if s.mikrotik_id else '-'
            })

        return {
            'success': True,
            'count': len(sub_list),
            'subscribers': sub_list
        }

    @http.route('/isp/pwa/api/invoices', type='json', auth='user')
    def get_invoices(self, q='', filter_state='unpaid', selected_company_id=None):
        """JSON API returning invoice list with Multi-Company support"""
        Invoice = request.env['account.move'].sudo()
        invoice_domain = self._get_invoice_company_domain(selected_company_id)

        domain = [
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted')
        ] + invoice_domain

        if filter_state == 'unpaid':
            domain.append(('payment_state', 'not in', ['paid', 'in_payment']))
        elif filter_state == 'paid':
            domain.append(('payment_state', 'in', ['paid', 'in_payment']))

        if q:
            domain.append('|')
            domain.append(('name', 'ilike', q))
            domain.append(('partner_id.name', 'ilike', q))

        invoices = Invoice.search(domain, order='invoice_date_due asc, id desc', limit=50)

        inv_list = []
        for inv in invoices:
            inv_list.append({
                'id': inv.id,
                'name': inv.name,
                'company_name': inv.company_id.name if inv.company_id else 'Global',
                'partner_name': inv.partner_id.name,
                'partner_id': inv.partner_id.id,
                'partner_mobile': inv.partner_id.mobile or inv.partner_id.phone or '',
                'amount_total': f"Rp {inv.amount_total:,.0f}".replace(",", "."),
                'amount_residual': f"Rp {inv.amount_residual:,.0f}".replace(",", "."),
                'invoice_date': inv.invoice_date.strftime('%d-%m-%Y') if inv.invoice_date else '-',
                'invoice_date_due': inv.invoice_date_due.strftime('%d-%m-%Y') if inv.invoice_date_due else '-',
                'payment_state': inv.payment_state,
                'wa_reminder_sent': inv.wa_reminder_sent,
                'wa_isolir_sent': inv.wa_isolir_sent,
            })

        return {
            'success': True,
            'count': len(inv_list),
            'invoices': inv_list
        }

    @http.route('/isp/pwa/api/test_router', type='json', auth='user')
    def test_router_connection(self, router_id):
        """Action endpoint to test connection to MikroTik router from Mobile PWA"""
        Router = request.env['isp.mikrotik.router'].sudo().browse(router_id)
        if not Router.exists():
            return {'success': False, 'message': 'Router tidak ditemukan'}
        try:
            Router.action_test_connection()
            return {
                'success': True,
                'message': f"Koneksi berhasil ke Router '{Router.name}' ({Router.host}:{Router.port})!",
                'new_status': Router.status
            }
        except Exception as e:
            return {
                'success': False,
                'message': f"Gagal terhubung ke Router '{Router.name}': {str(e)}",
                'new_status': 'error'
            }

    @http.route('/isp/pwa/api/sync_router_queues', type='json', auth='user')
    def sync_router_queues(self, router_id):
        """Action endpoint to sync simple queues from MikroTik from Mobile PWA"""
        Router = request.env['isp.mikrotik.router'].sudo().browse(router_id)
        if not Router.exists():
            return {'success': False, 'message': 'Router tidak ditemukan'}
        try:
            res = Router.action_sync_simple_queues()
            msg = res.get('params', {}).get('message', 'Sinkronisasi Simple Queue selesai!')
            return {
                'success': True,
                'message': msg
            }
        except Exception as e:
            return {
                'success': False,
                'message': f"Gagal sinkronisasi: {str(e)}"
            }

    @http.route('/isp/pwa/api/toggle_status', type='json', auth='user')
    def toggle_subscriber_status(self, partner_id, target_status):
        """1-Click Action endpoint from Mobile PWA to Isolir / Un-isolir subscriber"""
        Partner = request.env['res.partner'].sudo().browse(partner_id)
        if not Partner.exists() or not Partner.is_isp_subscriber:
            return {'success': False, 'message': 'Pelanggan tidak ditemukan'}

        if not Partner.mikrotik_id:
            return {'success': False, 'message': 'Router MikroTik belum dipasang untuk pelanggan ini'}

        # target_status: 'active' (enable / un-isolir) or 'isolated' (disable / isolir)
        enable = (target_status == 'active')
        success = Partner.mikrotik_id.set_subscriber_status(Partner, enable)

        if success:
            Partner.service_status = target_status
            msg = f"Layanan pelanggan '{Partner.name}' berhasil {'DIAKTIFKAN (Un-Isolir)' if enable else 'DIISOLIR'} di MikroTik & Odoo!"
            return {
                'success': True,
                'message': msg,
                'new_status': target_status
            }
        else:
            return {
                'success': False,
                'message': f"Gagal mengubah status di MikroTik '{Partner.mikrotik_id.name}'. Periksa log & jaringan."
            }

    @http.route('/isp/pwa/api/send_wa', type='json', auth='user')
    def send_wa_reminder(self, partner_id, message=None):
        """Triggers WhatsApp notification from Mobile PWA"""
        Partner = request.env['res.partner'].sudo().browse(partner_id)
        if not Partner.exists():
            return {'success': False, 'message': 'Pelanggan tidak ditemukan'}

        msg = message or f"Halo Bpk/Ibu {Partner.name}, ini adalah pengingat tagihan internet Anda dari Sistem Billing ISP. Terima kasih."
        success = Partner.send_wa_notification(msg)

        if success:
            return {'success': True, 'message': f"WhatsApp pengingat berhasil dikirim ke {Partner.name}!"}
        else:
            return {'success': False, 'message': f"Gagal mengirim WhatsApp ke {Partner.name}. Periksa nomor HP atau gateway WA."}
