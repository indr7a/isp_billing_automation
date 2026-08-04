# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError

class ISPSubscriberActionWizard(models.TransientModel):
    _name = 'isp.subscriber.action.wizard'
    _description = 'Konfirmasi Aksi Status Layanan ISP & Notifikasi WhatsApp'

    partner_id = fields.Many2one('res.partner', string="Pelanggan", required=True, readonly=True)
    action_type = fields.Selection([
        ('enable', 'Buka Isolir (Aktifkan Layanan)'),
        ('disable', 'Isolir Layanan (Pemblokiran Sementara)'),
        ('terminate', 'Putus Layanan (Terminated / Non-Aktif Permanen)')
    ], string="Aksi Layanan", required=True, readonly=True)

    send_wa = fields.Boolean(string="Kirim Notifikasi WhatsApp", default=True)
    wa_phone = fields.Char(related="partner_id.wa_phone", string="Nomor WhatsApp Tujuan", readonly=True)
    wa_message = fields.Text(string="Pesan WhatsApp", required=True)

    @api.model
    def default_get(self, fields_list):
        res = super(ISPSubscriberActionWizard, self).default_get(fields_list)
        active_id = self.env.context.get('active_id')
        action_type = self.env.context.get('default_action_type', 'enable')
        if active_id:
            partner = self.env['res.partner'].browse(active_id)
            res['partner_id'] = partner.id
            res['action_type'] = action_type
            ident = partner.ip_address or partner.ppp_username or partner.name
            
            if action_type == 'enable':
                res['wa_message'] = f"Yth. {partner.name}, layanan internet Anda ({ident}) telah DIAKTIFKAN KEMBALI secara manual oleh Admin."
            elif action_type == 'disable':
                res['wa_message'] = f"PERHATIAN: Layanan internet Anda ({ident}) telah DI-ISOLIR sementara oleh Admin."
            elif action_type == 'terminate':
                res['wa_message'] = f"PERHATIAN: Berlangganan layanan internet Anda ({ident}) telah DIPUTUS (Terminated) secara resmi oleh Admin."
        return res

    def action_confirm(self):
        """Executes MikroTik status change & sends WhatsApp if checked"""
        self.ensure_one()
        partner = self.partner_id

        if self.action_type == 'enable':
            if partner.mikrotik_id:
                partner.mikrotik_id.set_subscriber_status(partner, True)
            partner.service_status = 'active'
        elif self.action_type == 'disable':
            if partner.mikrotik_id:
                partner.mikrotik_id.set_subscriber_status(partner, False)
            partner.service_status = 'isolated'
        elif self.action_type == 'terminate':
            if partner.mikrotik_id:
                partner.mikrotik_id.set_subscriber_status(partner, False)
            partner.service_status = 'terminated'

        if self.send_wa and self.wa_message:
            partner.send_wa_notification(self.wa_message)

        return {'type': 'ir.actions.act_window_close'}
