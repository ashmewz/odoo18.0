# -*- coding: utf-8 -*-
{
    'name': 'Moodle Training',
    'version': '18.0.1.0.0',
    'category': 'Human Resources/Training',
    'summary': 'Sync Moodle course completions and raise compliance tickets',
    'description': """
Moodle Training
===============
* Connects Odoo to a Moodle LMS instance via its REST Web Services API.
* Syncs course completion records to employee profiles (matched by email).
* Raises internal compliance tickets for employees who have not completed
  required courses.
* Cron job runs automatically every hour; manual Sync Now also available.
    """,
    'depends': ['hr', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/cron.xml',
        'views/moodle_config_views.xml',
        'views/moodle_completion_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
