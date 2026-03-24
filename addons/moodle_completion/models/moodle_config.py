# -*- coding: utf-8 -*-
import requests

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MoodleConfig(models.Model):
    """
    Singleton model that stores the Moodle connection settings.
    Access via:  self.env['moodle.config'].get_config()
    """
    _name = 'moodle.config'
    _description = 'Moodle Connection Configuration'
    _rec_name = 'moodle_base_url'

    moodle_base_url = fields.Char(
        string='Moodle Base URL',
        required=True,
        help='Base URL of your Moodle instance, e.g. http://10.0.0.5',
    )
    moodle_token = fields.Char(
        string='Web Services Token',
        required=True,
        password=True,
        help='Token from Moodle: Site Admin → Plugins → Web services → Manage tokens',
    )
    active = fields.Boolean(default=True)

    # ------------------------------------------------------------------
    # Singleton helpers
    # ------------------------------------------------------------------

    @api.model
    def get_config(self):
        """Return the active config record or raise a clear error."""
        config = self.sudo().search([('active', '=', True)], limit=1)
        if not config:
            raise UserError(
                _('Moodle is not configured yet. '
                  'Go to Moodle Training → Settings and enter the Base URL and Token.')
            )
        return config

    # ------------------------------------------------------------------
    # API helper (shared by moodle_completion and helpdesk_ticket)
    # ------------------------------------------------------------------

    def call_api(self, function, extra_params=None):
        """
        Call a Moodle Web Services REST endpoint.

        :param function: Moodle wsfunction name, e.g. 'core_enrol_get_enrolled_users'
        :param extra_params: dict of additional POST parameters
        :returns: parsed JSON response (list or dict)
        :raises UserError: on connection or API-level errors
        """
        base_url = self.moodle_base_url.rstrip('/')
        endpoint = f'{base_url}/webservice/rest/server.php'
        payload = {
            'wstoken': self.moodle_token,
            'wsfunction': function,
            'moodlewsrestformat': 'json',
        }
        if extra_params:
            payload.update(extra_params)

        try:
            resp = requests.post(endpoint, data=payload, timeout=30)
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as exc:
            raise UserError(_('Cannot connect to Moodle at %s\n%s') % (base_url, exc)) from exc
        except requests.exceptions.Timeout:
            raise UserError(_('Connection to Moodle timed out. Check the Base URL.'))
        except requests.exceptions.RequestException as exc:
            raise UserError(_('Moodle request failed: %s') % exc) from exc

        result = resp.json()
        if isinstance(result, dict) and result.get('exception'):
            raise UserError(
                _('Moodle API error [%s]: %s') % (
                    result.get('errorcode', ''), result.get('message', ''))
            )
        return result

    # ------------------------------------------------------------------
    # Test connection action (called from Settings form button)
    # ------------------------------------------------------------------

    def action_test_connection(self):
        result = self.call_api('core_webservice_get_site_info')
        site_name = result.get('sitename', 'Unknown')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Connection Successful'),
                'message': _('Connected to: %s') % site_name,
                'sticky': False,
                'type': 'success',
            },
        }
