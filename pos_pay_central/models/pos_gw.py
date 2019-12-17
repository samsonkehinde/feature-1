# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class PosPaymentGatewayConfiguration(models.Model):
    _name = 'pos_pay_central.configuration'
    name = fields.Char(required=True, help='Name of this Payment Gateway Configuration')
    update_cycle = fields.Integer(string="Update Frequency" ,help="POS UI Transaction Update frequency in milliseconds")
    secret = fields.Char(string='Processor Secret',required=True, help='Processor Secret')
    payment_processor = fields.Selection([('fastpay','FastPay'),('paystack','paystack')],string='Payment Processor', help='Payment Processor')
    charge_url = fields.Char(string='Charge URL',required=True,help='Processor Charge Endpoint')
    verify_url = fields.Char(string='Verify URL',required=True,help='Processor Verify Endpoint')
    refund_url = fields.Char(string='Refund URL',required=True,help='Processor Refund Endpoint')
    otp_url = fields.Char(string='OTP URL', required=True, help='One Time PIN Endpoint')

class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    pos_payment_method = fields.Selection([('fastpay','FastPay'),('paystack','Paystack')],string='POS Method', help='POS Payment Method - FastPay, Paystack')
    pos_card_number = fields.Char(string='Card Number', help='The last 4 numbers of the Debit/Credit card used to pay or FastPay Account ID')
    pos_card_owner_name = fields.Char(string='Card/Account Owner', help='The name on the Debit/Credit Card or the FastPay Account Owner')
    pos_ref_no = fields.Char(string='Reference number', help='Payment reference number from Fast Pay/Paystack')
    pos_invoice_no = fields.Char(string='Invoice number', help='Order ID from Odoo')
    pos_sales_person = fields.Char(string='Terminal ID', help='Odoo User/Cashier')

class AccountJournal(models.Model):
    _inherit = 'account.journal'

    pos_pg_config_id = fields.Many2one('pos_pay_central.configuration', string='Payment Gateway Configuration', help='Payment Gateway Configuration for this POS.')

class PosOrder(models.Model):
    _inherit = "pos.order"

    @api.model
    def _payment_fields(self, ui_paymentline):
        fields = super(PosOrder, self)._payment_fields(ui_paymentline)

        fields.update({
            'payment_method': ui_paymentline.get('pos_payment_method'),
            'card_number': ui_paymentline.get('pos_card_number'),
            'card_owner_name': ui_paymentline.get('pos_card_owner_name'),
            'ref_no': ui_paymentline.get('pos_ref_no'),
            'invoice_no': ui_paymentline.get('pos_invoice_no'),
            'sales_person': ui_paymentline.get('pos_sales_person'),
        })

        return fields

    # Called by Order.AddPayment - pos_modal.py line 118, passing in the response from "_payment_fields" as parameter.
    def add_payment(self, data):
        statement_id = super(PosOrder, self).add_payment(data)
        statement_lines = self.env['account.bank.statement.line'].search([('statement_id', '=', statement_id),('pos_statement_id', '=', self.id),('journal_id', '=', data['journal']),('amount', '=', data['amount'])])

        for line in statement_lines:
            if not line.pos_payment_method:
                line.pos_payment_method = data.get('payment_method')
                line.pos_card_number = data.get('card_number')
                line.pos_card_owner_name = data.get('card_owner_name')
                line.pos_ref_no = data.get('ref_no')
                line.pos_invoice_no = data.get('invoice_no')
                line.pos_sales_person = data.get('sales_person')
                break

        return statement_id
