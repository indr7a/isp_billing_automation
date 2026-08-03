# -*- coding: utf-8 -*-
{
    'name': 'ISP Billing & MikroTik Automation',
    'version': '17.0.1.0.0',
    'category': 'Services/ISP',
    'summary': 'Automated ISP Billing, MikroTik PPP Isolation & WhatsApp Notifications',
    'description': """
        ISP Billing & MikroTik Automation Module for Odoo 17
        ====================================================
        * MikroTik Router Connection & Management via RouterOS API.
        * Automatic PPP User Enable/Disable (Isolir) based on invoice payment status.
        * WhatsApp Notifications for Payment Reminders (H-3), Overdue Notices, and Isolation/Reactivation alerts.
        * Automated Daily Cron Jobs for Billing Checks & Service Status Updating.
        * System Log & Audit Trail for Router & WhatsApp events.
    """,
    'author': 'Your ISP Engineering Team',
    'website': 'https://your-isp-domain.com',
    'depends': ['base', 'account', 'sale'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/cron_jobs.xml',
        'views/mikrotik_router_views.xml',
        'views/res_partner_views.xml',
        'views/account_move_views.xml',
        'views/isp_log_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu_items.xml',
    ],
    'external_dependencies': {
        'python': ['routeros_api', 'requests'],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
