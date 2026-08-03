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
    host = fields.Char(string="IP/Host/Tunnel Domain", required=True, help="IP Address, Domain, atau Tunnel Remote (misal: id-4.tunnel.id)")
    username = fields.Char(string="Username API", required=True, default="admin")
    password = fields.Char(string="Password API", required=True)
    port = fields.Integer(string="API Port", default=8728, required=True, help="Port API MikroTik (default 8728 atau port tunnel misal 682)")
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
            if hasattr(routeros_api, 'RouterOsApiPool'):
                connection = routeros_api.RouterOsApiPool(
                    self.host,
                    username=self.username,
                    password=self.password,
                    port=self.port,
                    plaintext_login=True
                )
                api = connection.get_api()
            elif hasattr(routeros_api, 'RouterOsApiConnection'):
                connection = routeros_api.RouterOsApiConnection(
                    self.host,
                    username=self.username,
                    password=self.password,
                    port=self.port
                )
                api = connection.connect()
            else:
                raise UserError("Versi library routeros_api tidak memiliki class RouterOsApiPool.")

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
            _logger.error(f"Failed to connect to MikroTik Router {self.name} ({self.host}:{self.port}): {str(e)}")
            raise UserError(f"Gagal terhubung ke Router MikroTik {self.name} ({self.host}:{self.port}): {str(e)}")

    def action_test_connection(self):
        """Test Connection Action Button"""
        for router in self:
            connection, api = router.get_connection()
            connection.disconnect()
            self.env['isp.log'].create({
                'source': 'mikrotik',
                'level': 'success',
                'message': f"Test koneksi berhasil ke MikroTik {router.name}",
                'details': f"Host/Tunnel: {router.host}:{router.port}"
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Koneksi Berhasil',
                    'message': f"Terhubung ke MikroTik {router.name} ({router.host}:{router.port})!",
                    'sticky': False,
                    'type': 'success'
                }
            }

    def set_subscriber_status(self, partner, status):
        """
        status: True for Enable (Un-isolir), False for Disable (Isolir)
        Supports both Static IP (Address List & Simple Queue) and PPPoE Secret.
        """
        self.ensure_one()
        if not partner:
            return False

        conntype = partner.connection_type or 'static'
        try:
            connection, api_conn = self.get_connection()

            if conntype == 'static':
                ip = partner.ip_address
                queue_name = partner.simple_queue_name

                if not ip and not queue_name:
                    _logger.warning(f"Partner {partner.name} does not have IP Address or Queue Name set.")
                    connection.disconnect()
                    return False

                # 1. Manage Firewall Address List (ISOLIR_LIST)
                if ip:
                    addr_resource = api_conn.get_resource('/ip/firewall/address-list')
                    existing = addr_resource.get(address=ip, list='ISOLIR_LIST')
                    if not status: # Isolir -> Add IP to ISOLIR_LIST
                        if not existing:
                            addr_resource.add(address=ip, list='ISOLIR_LIST', comment=f"Isolir Odoo: {partner.name}")
                            _logger.info(f"Added IP {ip} ({partner.name}) to MikroTik ISOLIR_LIST")
                    else: # Un-isolir -> Remove IP from ISOLIR_LIST
                        for ex in existing:
                            addr_resource.remove(id=ex['id'])
                            _logger.info(f"Removed IP {ip} ({partner.name}) from MikroTik ISOLIR_LIST")

                # 2. Manage Simple Queue (Disable / Enable)
                if queue_name:
                    queue_resource = api_conn.get_resource('/queue/simple')
                    queues = queue_resource.get(name=queue_name)
                    if queues:
                        target_state = 'no' if status else 'yes'
                        queue_resource.set(id=queues[0]['id'], disabled=target_state)
                        _logger.info(f"Simple Queue '{queue_name}' set disabled={target_state}")

                self.env['isp.log'].create({
                    'source': 'mikrotik',
                    'level': 'success' if status else 'warning',
                    'message': f"Status Static IP Pelanggan '{partner.name}' ({ip or queue_name}) diubah menjadi {'AKTIF' if status else 'ISOLIR'}",
                    'details': f"Router: {self.name} ({self.host}:{self.port}) | Mode: Static IP"
                })

            elif conntype == 'pppoe':
                ppp_username = partner.ppp_username
                if not ppp_username:
                    connection.disconnect()
                    return False

                ppp_resource = api_conn.get_resource('/ppp/secret')
                users = ppp_resource.get(name=ppp_username)
                if users:
                    user_id = users[0]['id']
                    target_state = 'no' if status else 'yes'
                    ppp_resource.set(id=user_id, disabled=target_state)
                    
                    if not status:
                        active_resource = api_conn.get_resource('/ppp/active')
                        active_users = active_resource.get(name=ppp_username)
                        for act in active_users:
                            active_resource.remove(id=act['id'])
                            
                    _logger.info(f"MikroTik PPP Secret '{ppp_username}' set disabled={target_state}")
                    
                    self.env['isp.log'].create({
                        'source': 'mikrotik',
                        'level': 'success' if status else 'warning',
                        'message': f"Status PPPoE User '{ppp_username}' diubah menjadi {'AKTIF' if status else 'ISOLIR'}",
                        'details': f"Router: {self.name} ({self.host}:{self.port}) | Mode: PPPoE"
                    })

            connection.disconnect()
            return True
        except Exception as e:
            _logger.error(f"Error setting status for subscriber {partner.name}: {str(e)}")
            self.env['isp.log'].create({
                'source': 'mikrotik',
                'level': 'error',
                'message': f"Gagal memperbarui status MikroTik untuk '{partner.name}'",
                'details': str(e)
            })
            return False
