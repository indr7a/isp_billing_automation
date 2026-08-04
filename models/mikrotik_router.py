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
    port = fields.Integer(string="API Port", default=8728, required=True, help="Port API MikroTik (default 8728 atau port remote tunnel API misal 682)")
    active = fields.Boolean(string="Active", default=True)
    
    status = fields.Selection([
        ('draft', 'Not Tested'),
        ('connected', 'Connected'),
        ('error', 'Connection Error')
    ], string="Status", default='draft', readonly=True)
    last_sync = fields.Datetime(string="Last Sync Date", readonly=True)

    def get_connection(self):
        """Creates RouterOS API Connection with fallback authentication support"""
        self.ensure_one()
        if not routeros_api:
            raise UserError("Library 'routeros_api' belum terinstal di server Python Odoo. Jalankan 'pip install routeros-api'.")
        try:
            # 1. Attempt Plaintext Login (RouterOS v6.43+ and v7.x)
            try:
                connection = routeros_api.RouterOsApiPool(
                    self.host,
                    username=self.username,
                    password=self.password,
                    port=self.port,
                    plaintext_login=True
                )
                api = connection.get_api()
            except Exception as e_pt:
                _logger.info(f"Plaintext API login failed for {self.host}:{self.port}, fallback to classic MD5 login: {str(e_pt)}")
                # 2. Fallback to Classic MD5 Challenge Login (RouterOS < v6.43)
                connection = routeros_api.RouterOsApiPool(
                    self.host,
                    username=self.username,
                    password=self.password,
                    port=self.port,
                    plaintext_login=False
                )
                api = connection.get_api()

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

    def action_sync_simple_queues(self):
        """Syncs / Imports Simple Queues from MikroTik into Odoo ResPartner subscribers"""
        for router in self:
            connection, api_conn = router.get_connection()
            try:
                queue_resource = api_conn.get_resource('/queue/simple')
                queues = queue_resource.get()
                
                Partner = self.env['res.partner']
                created_count = 0
                updated_count = 0
                
                for q in queues:
                    q_name = q.get('name')
                    q_target = q.get('target', '')
                    clean_ip = q_target.split('/')[0] if q_target else ''
                    
                    if not q_name:
                        continue

                    # Search existing partner by Simple Queue Name or IP Address or Name
                    domain = ['|', '|',
                        ('simple_queue_name', '=', q_name),
                        ('ip_address', '=', clean_ip),
                        ('name', '=', q_name)
                    ]
                    partner = Partner.search(domain, limit=1)
                    
                    values = {
                        'is_isp_subscriber': True,
                        'connection_type': 'static',
                        'mikrotik_id': router.id,
                        'simple_queue_name': q_name,
                        'ip_address': clean_ip or (partner.ip_address if partner else False),
                    }
                    
                    if partner:
                        partner.write(values)
                        updated_count += 1
                    else:
                        values['name'] = q_name
                        Partner.create(values)
                        created_count += 1

                connection.disconnect()

                self.env['isp.log'].create({
                    'source': 'mikrotik',
                    'level': 'success',
                    'message': f"Sinkronisasi Simple Queue MikroTik '{router.name}' berhasil",
                    'details': f"Dibuat: {created_count} pelanggan baru, Diperbarui: {updated_count} pelanggan"
                })

                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Sinkronisasi Berhasil',
                        'message': f"Berhasil menyinkronkan {len(queues)} Simple Queue dari MikroTik! ({created_count} baru, {updated_count} diperbarui)",
                        'sticky': False,
                        'type': 'success'
                    }
                }
            except Exception as e:
                connection.disconnect()
                _logger.error(f"Error syncing simple queues: {str(e)}")
                raise UserError(f"Gagal melakukan sinkronisasi Simple Queue: {str(e)}")

    def push_subscriber_to_mikrotik(self, partner):
        """
        Creates or updates configuration on MikroTik when adding/editing a subscriber in Odoo.
        - Static IP Mode: Creates/Updates /queue/simple (name, target IP, disabled)
        - PPPoE Mode: Creates/Updates /ppp/secret (name, password, profile, service=pppoe, disabled)
        """
        self.ensure_one()
        if not partner or not partner.is_isp_subscriber:
            return False

        conntype = partner.connection_type or 'static'
        connection, api_conn = self.get_connection()
        try:
            is_active = partner.service_status == 'active'
            disabled_str = 'no' if is_active else 'yes'

            if conntype == 'static':
                ip = partner.ip_address
                queue_name = partner.simple_queue_name or partner.name
                if not ip and not queue_name:
                    connection.disconnect()
                    raise UserError("IP Address atau Simple Queue Name harus diisi untuk mode Static IP.")

                target_ip = f"{ip}/32" if ip and '/' not in ip else (ip or "")
                queue_resource = api_conn.get_resource('/queue/simple')
                existing = queue_resource.get(name=queue_name)

                if existing:
                    queue_id = existing[0]['id']
                    update_vals = {'disabled': disabled_str}
                    if target_ip:
                        update_vals['target'] = target_ip
                    queue_resource.set(id=queue_id, **update_vals)
                    _logger.info(f"Updated Simple Queue '{queue_name}' on MikroTik {self.name}")
                else:
                    create_vals = {
                        'name': queue_name,
                        'target': target_ip or "0.0.0.0/0",
                        'disabled': disabled_str,
                        'comment': f"Created by Odoo: {partner.name}"
                    }
                    queue_resource.add(**create_vals)
                    _logger.info(f"Created new Simple Queue '{queue_name}' on MikroTik {self.name}")

                if not partner.simple_queue_name:
                    partner.simple_queue_name = queue_name

            elif conntype == 'pppoe':
                ppp_user = partner.ppp_username
                if not ppp_user:
                    connection.disconnect()
                    raise UserError("PPP Username harus diisi untuk mode PPPoE.")

                ppp_resource = api_conn.get_resource('/ppp/secret')
                existing = ppp_resource.get(name=ppp_user)
                
                profile_name = partner.isp_package_id.name if partner.isp_package_id else 'default'

                if existing:
                    user_id = existing[0]['id']
                    update_vals = {'disabled': disabled_str}
                    if partner.ppp_password:
                        update_vals['password'] = partner.ppp_password
                    ppp_resource.set(id=user_id, **update_vals)
                else:
                    create_vals = {
                        'name': ppp_user,
                        'password': partner.ppp_password or '123456',
                        'service': 'pppoe',
                        'profile': profile_name,
                        'disabled': disabled_str,
                        'comment': f"Created by Odoo: {partner.name}"
                    }
                    ppp_resource.add(**create_vals)

            connection.disconnect()
            self.env['isp.log'].create({
                'source': 'mikrotik',
                'level': 'success',
                'message': f"Push/Sync Pelanggan '{partner.name}' ke MikroTik {self.name} Berhasil",
                'details': f"Mode: {conntype.upper()} | Status: {partner.service_status}"
            })
            return True
        except Exception as e:
            connection.disconnect()
            _logger.error(f"Failed to push subscriber {partner.name} to MikroTik: {str(e)}")
            raise UserError(f"Gagal Push ke MikroTik: {str(e)}")

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
