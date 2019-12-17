# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date, timedelta

import requests
import werkzeug
import logging
import traceback

from odoo import models, api, service
from odoo.tools.translate import _
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, misc

_logger = logging.getLogger(__name__)


class PGTransactions(models.Model):
    _name = 'drugstoc_mobile.paystack_payment'

    def _setup_request(self, data):

        user = self.env['res.users'].sudo().browse(self.env.uid)

        if user and user.payment_gateway and user.payment_gateway.account_id and user.payment_gateway.journal_id:
            data['secret'] = user.payment_gateway.sudo().secret
            data['processor'] = user.payment_gateway.sudo().payment_processor
            data['account'] = user.payment_gateway.sudo().account_id.id
            data['journal'] = user.payment_gateway.sudo().journal_id.id

            # Set the processing url
            if data['type'] == "charge":
                data['proc_url'] = user.payment_gateway.sudo().charge_url
                data['verify_url'] = user.payment_gateway.sudo().verify_url

            elif data['type'] == "refund":
                data['proc_url'] = user.payment_gateway.sudo().refund_url

            else:
                data['proc_url'] = user.payment_gateway.sudo().otp_url

        else:
            raise UserError(_("Payment Gateway not set for user."))

    def process_request(self, template, trans_data):
        transaction_info = self.env.ref(template).render(trans_data).decode()

        #_logger.info(transaction_info)

        if not trans_data['processor'] or not trans_data['secret']:
            return {"status": "Setup Incomplete"}

        response = ''

        headers = {
            'Authorization': 'Bearer ' + trans_data['secret'],
            'Content-Type': 'application/json',
        }

        try:
            r = requests.post(trans_data['proc_url'], data=transaction_info, headers=headers, timeout=65)
            resp = r.json()

            #_logger.info(resp)

            # If a charge was attempted
            if resp['message'].lower() == "charge attempted":
                if resp['status']:  # If a positive response was received
                    if resp['data']['status'].lower() == "success":  # All Validation successful, process response

                        if trans_data['type'] == 'charge':
                            return self.verify_transaction(trans_data, headers, resp)

                        elif trans_data['type'] == 'send_otp':
                            return self.process_response(resp, trans_data)

                    elif resp['data']['status'].lower() == "send_otp":  # OTP Validation needed
                        return {"status": resp['data']['status'], "ref": resp['data']["reference"]}

                    elif resp['data']['status'].lower() == "pending":  # Timeout error
                        return {'status': resp['data']['message']}

                    elif resp['data']['status'].lower() == "send_pin":  # Incorrect PIN
                        return {'status': resp['data']['status']}

                else:  # If a negative response was received - Transaction Denied or Token not generated error.
                    return {'status': resp['data']['message']}

            elif resp['status'] and trans_data['type'] == 'refund':
                return {'status': 'Approved', "account": trans_data['account'], "journal": trans_data['journal']}

            else:
                return {'status': 'Unknown Error'}

        except Exception as e:
            # _logger.info(e)
            # _logger.info(r.text)
            return {"status": "timeout"}


    def verify_transaction(self, data, headers, resp):
        r = requests.get(data['verify_url'] + resp['data']['reference'], headers=headers, timeout=65)
        r.raise_for_status()
        resp = r.json()
        return self.process_response(resp, data)


    def process_response(self, resp, data):
        return {"status": "Approved", "card": resp['data']['authorization']['last4'], "ref": resp['data']["reference"],
                "processor": data['processor'], "account": data['account'], "journal": data['journal']}


    @api.model
    def send_otp(self, data):
        try:
            data['type'] = 'send_otp'
            self._setup_request(data)
        except Exception as e:
            #_logger.info(e)
            return {"status": "internal error"}
        response = self.process_request('drugstoc_mobile.send_otp', data)
        #_logger.info(response)
        return response


    @api.model
    def process_refund(self, data):
        try:
            data['type'] = 'refund'
            self._setup_request(data)
        except Exception as e:
            #_logger.info(e)
            return {"status": "internal error"}

        response = self.process_request('drugstoc_mobile.refund_transaction', data)
        #_logger.info(response)
        return response


    @api.model
    def process_payment(self, data):
        try:
            data['type'] = 'charge'
            self._setup_request(data)
            #_logger.info(data)
        except Exception as err:
            #_logger.info(err)
            return {"status": "no gateway"}

        response = self.process_request('drugstoc_mobile.charge_transaction', data)
        #_logger.info(response)
        return response

