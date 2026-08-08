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
        allowed_companies = user.company_ids
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
                    "src": "/isp_billing_automation/static/src/img/icon-192.png",
                    "sizes": "192x192",
                    "type": "image/png"
                },
                {
                    "src": "/isp_billing_automation/static/src/img/icon-512.png",
                    "sizes": "512x512",
                    "type": "image/png"
                }
            ]
        }
        return request.make_response(
            json.dumps(manifest),
            headers=[('Content-Type', 'application/json;charset=utf-8')]
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

    def _get_company_domain(self, selected_company_id=None):
        """Returns strict multi-company domain matching selected company or active user company"""
        user = request.env.user
        allowed_company_ids = user.company_ids.ids or [request.env.company.id]

        if selected_company_id and selected_company_id != 'all':
            try:
                comp_id = int(selected_company_id)
                if comp_id in allowed_company_ids:
                    return ['|', ('company_id', '=', False), ('company_id', '=', comp_id)]
            except (ValueError, TypeError):
                pass
        elif selected_company_id == 'all':
            return ['|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids)]

        # Default fallback if no company selected: use active session company
        session_comp_id = request.env.company.id
        return ['|', ('company_id', '=', False), ('company_id', '=', session_comp_id)]

    @http.route('/isp/pwa/api/dashboard', type='json', auth='user')
    def get_dashboard_data(self, selected_company_id=None):
        """JSON API returning real-time metrics for mobile dashboard with Multi-Company support"""
        Partner = request.env['res.partner'].sudo()
        Invoice = request.env['account.move'].sudo()
        Router = request.env['isp.mikrotik.router'].sudo()

        comp_domain = self._get_company_domain(selected_company_id)

        # Subscribers count
        domain_sub = [('is_isp_subscriber', '=', True)] + comp_domain
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
        ] + comp_domain

        monthly_invoices = Invoice.search(domain_inv_month)
        monthly_revenue = sum(monthly_invoices.mapped('amount_total'))

        unpaid_invoices = Invoice.search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'not in', ['paid', 'in_payment'])
        ] + comp_domain)

        total_unpaid_amount = sum(unpaid_invoices.mapped('amount_residual'))
        unpaid_count = len(unpaid_invoices)

        # Router statuses & per-router subscriber count
        routers = Router.search(comp_domain)
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

        # Top leaderboards
        dashboard_service = request.env['isp.dashboard.service'].sudo().create({})
        summary = dashboard_service.get_dashboard_summary()

        # Companies list for user switcher
        user_companies = [{
            'id': c.id,
            'name': c.name
        } for c in request.env.user.company_ids]

        current_company_name = request.env.company.name
        if selected_company_id and selected_company_id != 'all':
            try:
                comp_rec = request.env['res.company'].sudo().browse(int(selected_company_id))
                if comp_rec.exists():
                    current_company_name = comp_rec.name
            except Exception:
                pass
        elif selected_company_id == 'all':
            current_company_name = "Semua Perusahaan (Multi-Company)"

        return {
            'success': True,
            'user_name': request.env.user.name,
            'current_company_name': current_company_name,
            'selected_company_id': selected_company_id or str(request.env.company.id),
            'user_companies': user_companies,
            'total_subscribers': total_subscribers,
            'active_subscribers': active_subscribers,
            'isolated_subscribers': isolated_subscribers,
            'terminated_subscribers': terminated_subscribers,
            'monthly_revenue': f"Rp {monthly_revenue:,.0f}".replace(",", "."),
            'total_unpaid_amount': f"Rp {total_unpaid_amount:,.0f}".replace(",", "."),
            'unpaid_count': unpaid_count,
            'routers': router_data,
            'top_download': summary.get('top_download', [])[:5],
            'top_upload': summary.get('top_upload', [])[:5],
        }

    @http.route('/isp/pwa/api/subscribers', type='json', auth='user')
    def get_subscribers(self, q='', status='all', selected_company_id=None):
        """JSON API returning filtered subscriber list with Multi-Company support"""
        Partner = request.env['res.partner'].sudo()
        comp_domain = self._get_company_domain(selected_company_id)

        domain = [('is_isp_subscriber', '=', True)] + comp_domain
        
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
        comp_domain = self._get_company_domain(selected_company_id)

        domain = [
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted')
        ] + comp_domain

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
