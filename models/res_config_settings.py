# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    isp_wa_gateway_url = fields.Char(
        string="WhatsApp Gateway API URL",
        config_parameter='isp_wa_gateway_url',
        default="https://api.fonnte.com/send",
        help="Endpoint URL for sending HTTP POST WhatsApp notifications (e.g. Fonnte / Wablas)"
    )
    
    isp_wa_gateway_token = fields.Char(
        string="WhatsApp Gateway API Token",
        config_parameter='isp_wa_gateway_token',
        default="",
        help="Secret API Token / Key for WhatsApp Gateway service"
    )

    isp_isolation_grace_days = fields.Integer(
        string="Auto Isolation Grace Period (Days)",
        config_parameter='isp_isolation_grace_days',
        default=15,
        help="Days overdue after due date to execute MikroTik auto isolation"
    )
