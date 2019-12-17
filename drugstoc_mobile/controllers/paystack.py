import json
import base64
import logging
import requests
import werkzeug
from werkzeug.exceptions import Forbidden, NotFound
from odoo import fields, http, api, tools, _
from odoo.http import request

_logger = logging.getLogger(__name__)


class MobileAdapter(http.Controller):
    @http.route('/invoice/update/', type='http', auth='public', website=True)
    def update_invoice(self, **kw):
        ref = kw.get("reference")
        inv = http.request.env['account.invoice'].sudo().search([['payment_ref', '=', ref]], offset=0,
                                                                limit=0)
        if inv:
            # Get the payment_gateway config of the rep responsible for this sale\invoice
            gw = inv.user_id.payment_gateway
            if gw and gw.sudo().journal_id:

                # Verify Paystack Payment, ensure invoice amount equal to the amount paid
                headers = {
                    'Authorization': 'Bearer ' + gw.sudo().secret,
                    'Content-Type': 'application/json'
                }

                r = requests.get(gw.sudo().verify_url + ref, json={}, headers=headers, timeout=65)
                resp = r.json()

                _logger.info(kw.get("reference"))
                _logger.info(resp)

                # If a charge was attempted
                if resp['status'] and resp['message'].lower() == "verification successful" and resp[
                    'data']['amount'] >= inv.amount_total * 100:
                    # Once payment is confirmed, Create/Post Payment for this Invoice to the configured gw's journal.

                    inv.pay_and_reconcile(gw.journal_id.id)
                    inv.message_post(
                        body='Payment via Paystack<br/>Transaction Ref: <font color="red">' + str(ref) + '</font>')

                    return http.request.render('drugstoc_mobile.paystack_success', {'invoice': inv})
                else:
                    return http.request.render('drugstoc_mobile.paystack_error', {'msg': 'Unable to confirm payment.'})
            else:
                return http.request.render('drugstoc_mobile.paystack_error', {'msg': 'Configuration error.'})
        else:
            return http.request.render('drugstoc_mobile.paystack_error',
                                       {'msg': 'Your paystack payment could not complete.<br/>Reason: Invoice not found.'})
