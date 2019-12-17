# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Drugstoc Mobile',
    'version': '1.0',
    'category': 'Point of Sale',
    'author': 'Samson Kehinde',
    'sequence': 6,
    'summary': 'Ionic 3 Mobile App for Drugstoc Rep',
    'description': """
Integrates the Drugstoc Mobile App to Odoo.
================================================================================================================================

This module integrates the Drugstoc Mobile App to the Odoo platform to perform the following:

* View Customers.
* View Products.
* Add Products to Carts.
* Complete Invoices.
* Complete Orders.
* Complete Payments
* Add Calendar Events & Reps GPS Location Coords
    """,
    'depends': ['calendar','sale','pos_pay_central','website'],
    'website': 'www.softworks.com',
    'data': [
        'views/dsm_calendar_inherit.xml',
        'views/dsm_transaction_templates.xml',
        'views/dsm_views.xml',
        'views/dsm_user_inherit.xml',
        'views/paystack.xml'
    ],
    'demo': [
        'data/demo.xml',
    ],
    'qweb': [
    ],
    'installable': True,
    'auto_install': False,
}
