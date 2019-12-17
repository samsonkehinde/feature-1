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
    _name = 'pos_pay_central.payment_processor'

    def _get_pos_session(self):
        pos_session = self.env['pos.session'].search([('state', '=', 'opened'), ('user_id', '=', self.env.uid)],
                                                     limit=1)
        if not pos_session:
            raise UserError(_("No opened point of sale session for user %s found") % self.env.user.name)

        pos_session.login()

        return pos_session

    def _get_pos_pg_config_id(self, config, journal_id):
        journal = config.journal_ids.filtered(lambda r: r.id == journal_id)

        if journal and journal.pos_pg_config_id:
            return journal.pos_pg_config_id
        else:
            raise UserError(_("No Electronic Payment Gateway associated with the journal."))

    def _setup_request(self, data):
        pos_session = self._get_pos_session()

        config = pos_session.config_id
        pg_config = self._get_pos_pg_config_id(config, data['journal_id'])

        data['operator_id'] = pos_session.user_id.name
        data['secret'] = pg_config.sudo().secret
        data['processor'] = pg_config.sudo().payment_processor

        # Set the processing url
        if data['type'] == "charge":
            data['proc_url'] = pg_config.sudo().charge_url
            data['verify_url'] = pg_config.sudo().verify_url

        elif data['type'] == "refund":
            data['proc_url'] = pg_config.sudo().refund_url

        else:
            data['proc_url'] = pg_config.sudo().otp_url

    def process_request(self, template, trans_data):
        transaction_info = self.env.ref(template).render(trans_data).decode()
        _logger.info(transaction_info)
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
            _logger.info(resp)

            # If a charge was attempted
            if resp['message'].lower() == "charge attempted":
                if resp['status']:  # If a positive response was received
                    if resp['data']['status'].lower() == "success":# All Validation successful, process response
                        if trans_data['type'] == 'charge':
                            return self.verify_transaction(trans_data, headers, resp)
                        elif trans_data['type'] == 'send_otp':
                            return self.process_response(resp, trans_data)

                    elif resp['data']['status'].lower() == "send_otp":# OTP Validation needed
                        return {"status": resp['data']['status'],"ref": resp['data']["reference"]}

                    elif resp['data']['status'].lower() == "pending":# Timeout error
                        return {'status': resp['data']['message']}

                    elif resp['data']['status'].lower() == "send_pin":  # Incorrect PIN
                        return {'status': resp['data']['status']}

                else:   # If a negative response was received - Transaction Denied or Token not generated error.
                    return {'status': resp['data']['message']}
            elif resp['status'] and trans_data['type'] == 'refund':
                return {'status': 'Approved'}
            else:
                return {'status': 'Unknown Error'}

        except Exception as e:
            #_logger.info(e)
            #_logger.info(r.text)
            return {"status": "timeout"}

    def verify_transaction(self, data, headers, resp):
        r = requests.get(data['verify_url'] + resp['data']['reference'], headers=headers, timeout=65)
        r.raise_for_status()
        resp = r.json()
        return self.process_response(resp, data)

    def process_response(self, resp, data):
            return {"status": "Approved", "card": resp['data']['authorization']['last4'],
                    "ref": resp['data']["id"], "sales_person": data['operator_id'],
                    "processor": data['processor']}

    @api.model
    def send_otp(self, data):
        try:
            data['type'] = 'send_otp'
            self._setup_request(data)
        except Exception as e:
            #_logger.info(e)
            return {"status": "internal error"}
        response = self.process_request('pos_pay_central.send_otp', data)
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

        response = self.process_request('pos_pay_central.refund_transaction', data)
        _logger.info(response)
        return response

    @api.model
    def process_payment(self, data):
        try:
            data['type'] = 'charge'
            self._setup_request(data)
        except Exception as err:
            #_logger.info(err)
            return {"status": err}

        response = self.process_request('pos_pay_central.charge_transaction', data)
        #_logger.info(response)
        return response
