# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

try:
    import routeros_api
except ImportError:
    _logger.warning("routeros_api library is not installed. MikroTik integration will be disabled.")
    routeros_api = None


class MikrotikRouter(models.Model):
    _name = 'isp.mikrotik.router'
    _description = 'MikroTik Router Configuration'

    name = fields.Char(string="Router Name", required=True)
    host = fields.Char(string="IP/Host", required=True, help="IP Address or Domain Name of MikroTik Router")
    username = fields.Char(string="Username", required=True, default="admin")
    password = fields.Char(string="Password", required=True)
    port = fields.Integer(string="API Port", default=8728, required=True)
    active = fields.Boolean(string="Active", default=True)
    
    status = fields.Selection([
        ('connected', 'Connected'),
        ('error', 'Connection Error')
    ], string="Status", default='connected', readonly=True)
    last_sync = fields.Datetime(string="Last Sync Date", readonly=True)

    def get_connection(self):
        """Creates RouterOS API Connection"""
        self.ensure_one()
        if not routeros_api:
            raise UserError("Library 'routeros_api' belum terinstal di server Python Odoo. Jalankan 'pip install routeros-api'.")
        try:
            connection = routeros_api.RouterOsApiConnection(
                self.host, username=self.username, password=self.password, port=self.port
            )
            api = connection.connect()
            self.write({
                'status': 'connected',
                'last_sync': fields.Datetime.now()
            })
            return connection, api
        except Exception as e:
            self.write({
                'status': 'error',
                'last_sync': fields.Datetime.now()
            })
            _logger.error(f"Failed to connect to MikroTik Router {self.name} ({self.host}): {str(e)}")
            raise UserError(f"Gagal terhubung ke Router MikroTik {self.name} ({self.host}): {str(e)}")

    def action_test_connection(self):
        """Test Connection Action Button"""
        for router in self:
            connection, api = router.get_connection()
            connection.disconnect()
            self.env['isp.log'].create({
                'source': 'mikrotik',
                'level': 'success',
                'message': f"Test koneksi berhasil ke MikroTik {router.name}",
                'details': f"Host: {router.host}:{router.port}"
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Koneksi Berhasil',
                    'message': f"Terhubung ke MikroTik {router.name} ({router.host})!",
                    'sticky': False,
                    'type': 'success'
                }
            }

    def set_user_status(self, ppp_username, status):
        """
        status: True for Enable (Un-isolir), False for Disable (Isolir)
        """
        self.ensure_one()
        if not ppp_username:
            return False
        try:
            connection, api_conn = self.get_connection()
            ppp_resource = api_conn.get_resource('/ppp/secret')
            users = ppp_resource.get(name=ppp_username)
            if users:
                user_id = users[0]['id']
                target_state = 'no' if status else 'yes'
                ppp_resource.set(id=user_id, disabled=target_state)
                
                # Active connections cleanup if disabled (disconnect active session)
                if not status:
                    active_resource = api_conn.get_resource('/ppp/active')
                    active_users = active_resource.get(name=ppp_username)
                    for act in active_users:
                        active_resource.remove(id=act['id'])
                        
                _logger.info(f"MikroTik PPP Secret '{ppp_username}' set disabled={target_state}")
                
                # Log to isp.log table
                self.env['isp.log'].create({
                    'source': 'mikrotik',
                    'level': 'success' if status else 'warning',
                    'message': f"Status MikroTik User '{ppp_username}' diubah menjadi {'AKTIFF' if status else 'ISOLIR (Disabled)'}",
                    'details': f"Router: {self.name} ({self.host})"
                })
            else:
                _logger.warning(f"PPP Secret '{ppp_username}' not found on router {self.name}")
                self.env['isp.log'].create({
                    'source': 'mikrotik',
                    'level': 'error',
                    'message': f"PPP Secret '{ppp_username}' tidak ditemukan di Router {self.name}",
                    'details': f"Host: {self.host}"
                })
                connection.disconnect()
                return False

            connection.disconnect()
            return True
        except Exception as e:
            _logger.error(f"Error setting PPP status for {ppp_username}: {str(e)}")
            self.env['isp.log'].create({
                'source': 'mikrotik',
                'level': 'error',
                'message': f"Gagal memperbarui MikroTik PPP '{ppp_username}'",
                'details': str(e)
            })
            return False
