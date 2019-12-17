# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class DSM_Users(models.Model):
    _inherit = "res.users"

    payment_gateway = fields.Many2one('pos_pay_central.configuration', string='Payment Gateway',
                                      help='Payment Gateway to be used by the user in the Drugstoc Mobile app')


class DSM_PSC(models.Model):
    _inherit = "pos_pay_central.configuration"

    account_id = fields.Many2one('account.account', string='Revenue Account',
                                 help='Account into which to receive the gateway transactions as used in the Journal Entry UI.')
    journal_id = fields.Many2one('account.journal', string='Revenue Journal',
                                 help='Journal into which to record the gateway transactions as specified in the Invoice Payment UI.')


class DSM_Account_Invoice(models.Model):
    _inherit = "account.invoice"
    payment_ref = fields.Char(string='Payment Reference', help='Paystack Payment Reference')
