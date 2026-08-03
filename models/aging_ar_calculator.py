# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ISPAccountMoveAging(models.Model):
    _inherit = 'account.move'

    @api.model
    def get_aging_ar_summary(self):
        """Returns Aging Accounts Receivable report aggregated into 4 ISP stages"""
        today = fields.Date.today()
        invoices = self.search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'not in', ['paid', 'in_payment', 'reversed']),
            ('is_isp_invoice', '=', True)
        ])
        
        aging = {
            'current': {'label': 'Current / Belum Jatuh Tempo', 'amount': 0.0, 'count': 0},
            '1_15_days': {'label': 'Overdue 1 - 15 Hari (Tahap Warning)', 'amount': 0.0, 'count': 0},
            '16_30_days': {'label': 'Overdue 16 - 30 Hari (Tahap Isolir)', 'amount': 0.0, 'count': 0},
            'over_30_days': {'label': 'Overdue > 30 Hari (Kritis / Macet)', 'amount': 0.0, 'count': 0}
        }
        
        for inv in invoices:
            if not inv.invoice_date_due:
                continue
            days_overdue = (today - inv.invoice_date_due).days
            amount = inv.amount_residual or inv.amount_total
            
            if days_overdue <= 0:
                aging['current']['amount'] += amount
                aging['current']['count'] += 1
            elif 1 <= days_overdue <= 15:
                aging['1_15_days']['amount'] += amount
                aging['1_15_days']['count'] += 1
            elif 16 <= days_overdue <= 30:
                aging['16_30_days']['amount'] += amount
                aging['16_30_days']['count'] += 1
            else:
                aging['over_30_days']['amount'] += amount
                aging['over_30_days']['count'] += 1

        return aging
