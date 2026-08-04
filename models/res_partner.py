# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)

class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_isp_subscriber = fields.Boolean(string="ISP Subscriber", default=False, index=True)
    connection_type = fields.Selection([
        ('static', 'Static IP / Simple Queue'),
        ('pppoe', 'PPPoE Secret')
    ], string="Connection Type", default='static', required=True)

    ip_address = fields.Char(string="Static IP Address", help="IP Address Pelanggan (misal: 192.168.10.50)")
    simple_queue_name = fields.Char(string="Simple Queue Name", help="Nama Simple Queue di MikroTik")
    ppp_username = fields.Char(string="PPP Username", index=True, help="Username PPPoE jika menggunakan mode PPPoE")
    ppp_password = fields.Char(string="PPP Password", help="Password untuk akun PPPoE pelanggan di MikroTik")

    mikrotik_id = fields.Many2one('isp.mikrotik.router', string="Assigned MikroTik Router", domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")
    service_status = fields.Selection([
        ('active', 'Active'),
        ('isolated', 'Isolated (Isolir)'),
        ('terminated', 'Terminated (Putus)')
    ], string="ISP Service Status", default='active', index=True)
    
    isp_package_id = fields.Many2one('product.product', string="Internet Package", domain="[('type', '=', 'service')]")
    monthly_fee = fields.Float(string="Monthly Subscription Fee", help="Tarif iuran bulanan riil untuk pelanggan ini (Otomatis terisi dari Sales Price produk, namun bisa disesuaikan manual)")
    wa_phone = fields.Char(string="WhatsApp Phone", help="Nomor WhatsApp kontak pelanggan (misal: 628123456789)")

    @api.onchange('is_isp_subscriber')
    def _onchange_is_isp_subscriber(self):
        """Auto-bind partner company_id when ISP Subscriber is enabled"""
        if self.is_isp_subscriber and not self.company_id:
            self.company_id = self.env.company

    @api.onchange('isp_package_id')
    def _onchange_isp_package_id(self):
        """Auto-fill monthly_fee from product sales price (lst_price) when package changes"""
        if self.isp_package_id:
            self.monthly_fee = self.isp_package_id.lst_price

    def action_sync_to_mikrotik(self):
        """Creates or updates subscriber config directly on MikroTik from Odoo"""
        for partner in self:
            if not partner.is_isp_subscriber:
                raise UserError("Kontak ini bukan merupakan Pelanggan ISP.")
            if not partner.mikrotik_id:
                raise UserError("Silakan pilih Router MikroTik terlebih dahulu.")
            
            partner.mikrotik_id.push_subscriber_to_mikrotik(partner)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sync MikroTik Berhasil',
                    'message': f"Konfigurasi pelanggan '{partner.name}' telah berhasil di-push / dibuat di Router MikroTik {partner.mikrotik_id.name}!",
                    'sticky': False,
                    'type': 'success'
                }
            }

    def send_wa_notification(self, message):
        """Sends WhatsApp message via fs_whatsapp_connector (whatsapp.account) or fallback HTTP Gateway"""
        self.ensure_one()
        phone = self.wa_phone or self.mobile or self.phone
        if not phone:
            _logger.warning(f"No phone number configured for partner {self.name}")
            return False
            
        phone = phone.replace('+', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
        if phone.startswith('08'):
            phone = '628' + phone[2:]

        # 1. Integration with fs_whatsapp_connector (whatsapp.account)
        if 'whatsapp.account' in self.env:
            try:
                wa_account = self.env['whatsapp.account'].sudo().get_active_account()
                if wa_account:
                    payload = {
                        'phone': phone,
                        'message': message
                    }
                    res = wa_account.api_post('/send/message', payload)
                    _logger.info(f"WA sent via fs_whatsapp_connector to {phone}. Response: {res}")
                    self.env['isp.log'].create({
                        'source': 'whatsapp',
                        'level': 'info',
                        'company_id': self.company_id.id if self.company_id else self.env.company.id,
                        'message': f"WhatsApp Terkirim (fs_whatsapp_connector) ke {self.name} ({phone})",
                        'details': f"Pesan: {message}\nAccount: {wa_account.name} (Device: {wa_account.device_id})\nResponse: {res}"
                    })
                    return True
            except Exception as e_fs:
                _logger.warning(f"Failed sending via fs_whatsapp_connector: {str(e_fs)}. Trying fallback HTTP gateway...")

        # 2. Fallback to System Parameters HTTP Gateway API (Fonnte / Wablas)
        icp = self.env['ir.config_parameter'].sudo()
        wa_url = icp.get_param('isp_wa_gateway_url', 'https://api.fonnte.com/send')
        wa_token = icp.get_param('isp_wa_gateway_token', '')

        if not wa_token:
            _logger.warning("WhatsApp Gateway Token is not set in System Settings.")
            self.env['isp.log'].create({
                'source': 'whatsapp',
                'level': 'warning',
                'company_id': self.company_id.id if self.company_id else self.env.company.id,
                'message': f"WA Not Send (No Token/Account) to {self.name} ({phone})",
                'details': f"Content: {message}"
            })
            return False

        headers = {'Authorization': wa_token}
        payload = {
            'target': phone,
            'message': message
        }
        
        try:
            response = requests.post(wa_url, data=payload, headers=headers, timeout=10)
            _logger.info(f"WA sent to {phone}. Response: {response.text}")
            
            self.env['isp.log'].create({
                'source': 'whatsapp',
                'level': 'info',
                'company_id': self.company_id.id if self.company_id else self.env.company.id,
                'message': f"WhatsApp Notifikasi Terkirim ke {self.name} ({phone})",
                'details': f"Pesan: {message}\nResponse API: {response.text}"
            })
            return True
        except Exception as e:
            _logger.error(f"Failed to send WA to {phone}: {str(e)}")
            self.env['isp.log'].create({
                'source': 'whatsapp',
                'level': 'error',
                'company_id': self.company_id.id if self.company_id else self.env.company.id,
                'message': f"Gagal Kirim WhatsApp ke {self.name} ({phone})",
                'details': str(e)
            })
            return False

    def action_manual_enable_service(self):
        """Manual Un-isolir / Activate Button via Confirmation Wizard"""
        self.ensure_one()
        return {
            'name': 'Konfirmasi Buka Isolir Layanan',
            'type': 'ir.actions.act_window',
            'res_model': 'isp.subscriber.action.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'default_action_type': 'enable',
            }
        }

    def action_manual_disable_service(self):
        """Manual Isolir Button via Confirmation Wizard"""
        self.ensure_one()
        return {
            'name': 'Konfirmasi Isolir Layanan',
            'type': 'ir.actions.act_window',
            'res_model': 'isp.subscriber.action.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'default_action_type': 'disable',
            }
        }

    def action_manual_terminate_service(self):
        """Manual Terminate Service Button via Confirmation Wizard"""
        self.ensure_one()
        return {
            'name': 'Konfirmasi Pemutusan Layanan (Terminate)',
            'type': 'ir.actions.act_window',
            'res_model': 'isp.subscriber.action.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'default_action_type': 'terminate',
            }
        }
