# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ISPLog(models.Model):
    _name = 'isp.log'
    _description = 'ISP System & Activity Log'
    _order = 'timestamp desc, id desc'

    name = fields.Char(string="Title", compute="_compute_name", store=True)
    timestamp = fields.Datetime(string="Timestamp", default=fields.Datetime.now, required=True, index=True)
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.company, index=True)
    source = fields.Selection([
        ('mikrotik', 'MikroTik Router'),
        ('whatsapp', 'WhatsApp Gateway'),
        ('system', 'System Cron / Billing')
    ], string="Log Source", required=True, default='system')
    
    level = fields.Selection([
        ('info', 'Info'),
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('error', 'Error')
    ], string="Log Level", required=True, default='info')

    message = fields.Char(string="Message Summary", required=True)
    details = fields.Text(string="Detailed Output / Payload")

    @api.depends('source', 'level', 'message')
    def _compute_name(self):
        for rec in self:
            rec.name = f"[{rec.source.upper() if rec.source else 'LOG'}] {rec.message or ''}"
