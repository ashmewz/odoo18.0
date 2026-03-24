# -*- coding: utf-8 -*-
import logging
from datetime import datetime

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MoodleCompletion(models.Model):
    _name = 'moodle.completion'
    _description = 'Moodle Course Completion Record'
    _order = 'completion_date desc, employee_name asc'
    _rec_name = 'employee_name'

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        ondelete='set null',
        help='Matched automatically by Moodle user email → employee work email.',
    )
    employee_name = fields.Char(string='Moodle Full Name', readonly=True)
    moodle_user_id = fields.Integer(string='Moodle User ID', readonly=True, index=True)
    moodle_email = fields.Char(string='Moodle Email', readonly=True)
    course_id = fields.Integer(string='Moodle Course ID', readonly=True, index=True)
    course_name = fields.Char(string='Course Name', readonly=True)
    completed = fields.Boolean(string='Completed', readonly=True)
    completion_date = fields.Datetime(string='Completion Date', readonly=True)
    status = fields.Selection(
        selection=[
            ('not_started', 'Not Started'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
        ],
        string='Status',
        default='not_started',
        readonly=True,
    )
    last_synced = fields.Datetime(string='Last Synced', readonly=True)
    ticket_ids = fields.One2many(
        'moodle.ticket',
        'completion_id',
        string='Compliance Tickets',
    )
    ticket_count = fields.Integer(
        string='Tickets',
        compute='_compute_ticket_count',
    )

    _sql_constraints = [
        (
            'unique_moodle_user_course',
            'UNIQUE(moodle_user_id, course_id)',
            'A completion record already exists for this Moodle user and course.',
        ),
    ]

    # ------------------------------------------------------------------
    # Computed
    # ------------------------------------------------------------------

    @api.depends('ticket_ids')
    def _compute_ticket_count(self):
        for rec in self:
            rec.ticket_count = len(rec.ticket_ids)

    # ------------------------------------------------------------------
    # Main sync
    # ------------------------------------------------------------------

    @api.model
    def _sync_moodle_completions(self):
        """
        Entry point called by the cron job and by Sync Now.
        Reads comma-separated course IDs from the system parameter
        ``moodle.course_ids`` (e.g. ``3`` or ``3,7,12``).
        """
        ICP = self.env['ir.config_parameter'].sudo()
        config = self.env['moodle.config'].get_config()

        course_ids_str = ICP.get_param('moodle.course_ids', '').strip()
        if not course_ids_str:
            _logger.warning(
                'moodle_completion: No course IDs configured. '
                'Set system parameter "moodle.course_ids" (e.g. 3 or 3,7,12).'
            )
            return

        course_ids = [
            int(c.strip())
            for c in course_ids_str.split(',')
            if c.strip().isdigit()
        ]

        for course_id in course_ids:
            try:
                self._sync_single_course(config, course_id)
            except UserError as exc:
                _logger.error(
                    'moodle_completion: Error syncing course %s — %s', course_id, exc
                )

    def _sync_single_course(self, config, course_id):
        """Fetch and upsert completion records for one Moodle course."""
        # Course name
        course_list = config.call_api(
            'core_course_get_courses',
            {'options[ids][0]': course_id},
        )
        course_name = course_list[0]['fullname'] if course_list else f'Course {course_id}'

        # Enrolled users
        enrolled_users = config.call_api(
            'core_enrol_get_enrolled_users',
            {'courseid': course_id},
        )
        if not enrolled_users:
            _logger.info('moodle_completion: No enrolled users for course %s.', course_id)
            return

        now = fields.Datetime.now()

        for user in enrolled_users:
            moodle_uid = user.get('id')
            email = (user.get('email') or '').strip().lower()
            fullname = user.get('fullname', '')

            # Per-user completion status
            completed = False
            completion_date = False
            status = 'not_started'
            try:
                comp_data = config.call_api(
                    'core_completion_get_course_completion_status',
                    {'courseid': course_id, 'userid': moodle_uid},
                )
                status_obj = comp_data.get('completionstatus', {})
                completed = bool(status_obj.get('completed', False))

                if completed:
                    status = 'completed'
                    for comp in status_obj.get('completions', []):
                        ts = comp.get('timecompleted')
                        if ts:
                            try:
                                completion_date = datetime.utcfromtimestamp(int(ts))
                            except (ValueError, OSError):
                                pass
                            break
                else:
                    any_done = any(c.get('complete') for c in status_obj.get('completions', []))
                    status = 'in_progress' if any_done else 'not_started'

            except UserError as exc:
                _logger.warning(
                    'moodle_completion: Could not get completion for user %s '
                    'in course %s — %s', moodle_uid, course_id, exc
                )

            # Match employee by work email
            employee = False
            if email:
                employee = self.env['hr.employee'].sudo().search(
                    [('work_email', '=ilike', email)], limit=1
                )

            # Upsert
            existing = self.sudo().search(
                [('moodle_user_id', '=', moodle_uid), ('course_id', '=', course_id)],
                limit=1,
            )
            vals = {
                'moodle_user_id': moodle_uid,
                'moodle_email': email,
                'employee_name': fullname,
                'course_id': course_id,
                'course_name': course_name,
                'completed': completed,
                'completion_date': completion_date,
                'status': status,
                'employee_id': employee.id if employee else False,
                'last_synced': now,
            }
            if existing:
                existing.sudo().write(vals)
            else:
                self.sudo().create(vals)

        _logger.info(
            'moodle_completion: Synced "%s" (course %s) — %d users.',
            course_name, course_id, len(enrolled_users),
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_sync_now(self):
        self.env['moodle.completion']._sync_moodle_completions()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sync Complete'),
                'message': _('Moodle completion records have been synchronised.'),
                'sticky': False,
                'type': 'success',
            },
        }

    def action_view_tickets(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Compliance Tickets'),
            'res_model': 'moodle.ticket',
            'view_mode': 'list,form',
            'domain': [('completion_id', 'in', self.ids)],
            'context': {'default_completion_id': self.id},
        }

    def action_create_ticket(self):
        """Create a compliance ticket for this (non-completed) record."""
        self.ensure_one()
        if self.completed:
            raise UserError(_('This employee has already completed the course.'))
        ticket = self.env['moodle.ticket'].sudo().create({
            'name': _('Compliance: %s — %s') % (self.course_name, self.employee_name),
            'completion_id': self.id,
            'employee_id': self.employee_id.id,
            'description': _(
                'Employee "%s" has not completed the required course "%s".'
            ) % (self.employee_name, self.course_name),
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Compliance Ticket'),
            'res_model': 'moodle.ticket',
            'res_id': ticket.id,
            'view_mode': 'form',
        }
