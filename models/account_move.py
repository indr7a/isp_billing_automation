# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    is_isp_invoice = fields.Boolean(string="ISP Invoice", default=False, index=True)
    wa_reminder_sent = fields.Boolean(string="WA H-3 Reminder Sent", default=False)
    wa_isolir_sent = fields.Boolean(string="WA Isolir Sent", default=False)

    def _action_reopen_service(self):
        """Re-enables internet service on MikroTik & sends WA Thank You reactivation message"""
        for inv in self:
            partner = inv.partner_id
            if partner.is_isp_subscriber and partner.ppp_username and partner.mikrotik_id:
                success = partner.mikrotik_id.set_user_status(partner.ppp_username, True)
                if success:
                    partner.service_status = 'active'
                    wa_msg = "Terima kasih. Layanan internet telah diaktifkan kembali secara otomatis."
                    partner.send_wa_notification(wa_msg)

    def write(self, vals):
        res = super(AccountMove, self).write(vals)
        if 'payment_state' in vals or 'state' in vals:
            for rec in self:
                if rec.is_isp_invoice and rec.payment_state in ['paid', 'in_payment']:
                    rec._action_reopen_service()
        return res

    @api.model
    def _cron_isp_billing_process(self):
        """Scheduled Action runner: H-3 WhatsApp Reminder & Overdue Isolation Execution"""
        today = fields.Date.today()
        icp = self.env['ir.config_parameter'].sudo()
        grace_days = int(icp.get_param('isp_isolation_grace_days', 15))

        # 1. Scan H-3 Reminder (Due in 3 days)
        due_reminder_date = today + timedelta(days=3)
        reminder_invoices = self.search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'not in', ['paid', 'in_payment', 'reversed']),
            ('invoice_date_due', '=', due_reminder_date),
            ('is_isp_invoice', '=', True),
            ('wa_reminder_sent', '=', False)
        ])
        
        for inv in reminder_invoices:
            partner = inv.partner_id
            bulan_str = inv.invoice_date.strftime('%B %Y') if inv.invoice_date else today.strftime('%B %Y')
            nominal_str = f"Rp {inv.amount_total:,.0f}"
            tanggal_str = inv.invoice_date_due.strftime('%d-%m-%Y') if inv.invoice_date_due else "-"

            msg = (
                "Pengingat otomatis dari Sistem Billing.\n\n"
                f"Invoice internet periode {bulan_str} sebesar {nominal_str} akan jatuh tempo pada "
                f"{tanggal_str}. Mohon melakukan pembayaran sebelum jatuh tempo agar layanan tetap aktif."
            )
            if partner.send_wa_notification(msg):
                inv.wa_reminder_sent = True

        # 2. Scan Overdue Isolation (Overdue >= grace_days)
        isolation_threshold_date = today - timedelta(days=grace_days)
        invoices_to_isolate = self.search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'not in', ['paid', 'in_payment', 'reversed']),
            ('invoice_date_due', '<=', isolation_threshold_date),
            ('is_isp_invoice', '=', True)
        ])
        
        for inv in invoices_to_isolate:
            partner = inv.partner_id
            if partner.is_isp_subscriber and partner.mikrotik_id and partner.service_status != 'isolated':
                success = partner.mikrotik_id.set_user_status(partner.ppp_username, False)
                if success:
                    partner.service_status = 'isolated'
                    inv.wa_isolir_sent = True
                    msg = (
                        "Layanan internet Anda telah diisolir secara otomatis oleh sistem karena invoice "
                        "telah melewati batas pembayaran. Setelah pembayaran diterima, layanan akan aktif "
                        "kembali secara otomatis."
                    )
                    partner.send_wa_notification(msg)
