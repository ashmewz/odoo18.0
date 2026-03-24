# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class MoodleTicket(models.Model):
    """
    Internal compliance ticket raised when an employee has not completed
    a required Moodle course.  Works without the Enterprise Helpdesk module.
    """
    _name = 'moodle.ticket'
    _description = 'Moodle Compliance Ticket'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'name'

    name = fields.Char(string='Subject', required=True, tracking=True)
    completion_id = fields.Many2one(
        'moodle.completion',
        string='Completion Record',
        ondelete='cascade',
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        tracking=True,
    )
    description = fields.Text(string='Description')
    state = fields.Selection(
        selection=[
            ('open', 'Open'),
            ('in_progress', 'In Progress'),
            ('resolved', 'Resolved'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='open',
        tracking=True,
    )
    priority = fields.Selection(
        selection=[
            ('0', 'Normal'),
            ('1', 'High'),
            ('2', 'Critical'),
        ],
        string='Priority',
        default='0',
    )
    assigned_to = fields.Many2one(
        'res.users',
        string='Assigned To',
        default=lambda self: self.env.user,
        tracking=True,
    )
    course_name = fields.Char(
        string='Course',
        related='completion_id.course_name',
        store=True,
    )
    deadline = fields.Date(string='Deadline')

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def action_set_in_progress(self):
        self.write({'state': 'in_progress'})

    def action_set_resolved(self):
        self.write({'state': 'resolved'})

    def action_set_cancelled(self):
        self.write({'state': 'cancelled'})

    def action_reopen(self):
        self.write({'state': 'open'})

    # ------------------------------------------------------------------
    # Bulk ticket creation from completion records
    # ------------------------------------------------------------------

    @api.model
    def create_tickets_for_non_compliant(self):
        """
        Creates (or skips existing) compliance tickets for every
        moodle.completion record where status != 'completed' and an
        employee is matched.  Called manually or via a server action.
        """
        non_compliant = self.env['moodle.completion'].sudo().search([
            ('status', '!=', 'completed'),
            ('employee_id', '!=', False),
        ])
        created = 0
        for rec in non_compliant:
            already_open = self.sudo().search([
                ('completion_id', '=', rec.id),
                ('state', 'not in', ['resolved', 'cancelled']),
            ], limit=1)
            if already_open:
                continue
            self.sudo().create({
                'name': _('Compliance: %s — %s') % (rec.course_name, rec.employee_name),
                'completion_id': rec.id,
                'employee_id': rec.employee_id.id,
                'description': _(
                    'Employee "%s" has not completed the required course "%s".'
                ) % (rec.employee_name, rec.course_name),
            })
            created += 1
        return created
