# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)

class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_isp_subscriber = fields.Boolean(string="ISP Subscriber", default=False, index=True)
    ppp_username = fields.Char(string="PPP Username", index=True)
    mikrotik_id = fields.Many2one('isp.mikrotik.router', string="Assigned MikroTik Router")
    service_status = fields.Selection([
        ('active', 'Active'),
        ('isolated', 'Isolated (Isolir)'),
        ('terminated', 'Terminated')
    ], string="ISP Service Status", default='active', index=True)
    
    isp_package_id = fields.Many2one('product.product', string="Internet Package", domain="[('type', '=', 'service')]")
    monthly_fee = fields.Float(string="Monthly Subscription Fee")
    wa_phone = fields.Char(string="WhatsApp Phone", help="WhatsApp contact number (e.g. 628123456789)")

    def send_wa_notification(self, message):
        """Sends WhatsApp message via Gateway API (e.g. Fonnte / Wablas)"""
        self.ensure_one()
        phone = self.wa_phone or self.mobile or self.phone
        if not phone:
            _logger.warning(f"No phone number configured for partner {self.name}")
            return False
            
        # Clean phone format
        phone = phone.replace('+', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
        if phone.startswith('08'):
            phone = '628' + phone[2:]

        icp = self.env['ir.config_parameter'].sudo()
        wa_url = icp.get_param('isp_wa_gateway_url', 'https://api.fonnte.com/send')
        wa_token = icp.get_param('isp_wa_gateway_token', '')

        if not wa_token:
            _logger.warning("WhatsApp Gateway Token is not set in System Settings.")
            # Still record log for simulation/traceability
            self.env['isp.log'].create({
                'source': 'whatsapp',
                'level': 'warning',
                'message': f"WA Not Send (No Token) to {self.name} ({phone})",
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
                'message': f"WhatsApp Notifikasi Terkirim ke {self.name} ({phone})",
                'details': f"Pesan: {message}\nResponse API: {response.text}"
            })
            return True
        except Exception as e:
            _logger.error(f"Failed to send WA to {phone}: {str(e)}")
            self.env['isp.log'].create({
                'source': 'whatsapp',
                'level': 'error',
                'message': f"Gagal Kirim WhatsApp ke {self.name} ({phone})",
                'details': str(e)
            })
            return False

    def action_manual_enable_service(self):
        """Manual Un-isolir Button"""
        for partner in self:
            if not partner.mikrotik_id or not partner.ppp_username:
                raise UserError("Partner belum dikonfigurasi MikroTik Router atau PPP Username.")
            success = partner.mikrotik_id.set_user_status(partner.ppp_username, True)
            if success:
                partner.service_status = 'active'
                wa_msg = f"Yth. {partner.name}, layanan internet Anda ({partner.ppp_username}) telah DIAKTIFKAN KEMBALI secara manual oleh Admin."
                partner.send_wa_notification(wa_msg)

    def action_manual_disable_service(self):
        """Manual Isolir Button"""
        for partner in self:
            if not partner.mikrotik_id or not partner.ppp_username:
                raise UserError("Partner belum dikonfigurasi MikroTik Router atau PPP Username.")
            success = partner.mikrotik_id.set_user_status(partner.ppp_username, False)
            if success:
                partner.service_status = 'isolated'
                wa_msg = f"PERHATIAN: Layanan internet Anda ({partner.ppp_username}) telah DI-ISOLIR oleh Admin."
                partner.send_wa_notification(wa_msg)
