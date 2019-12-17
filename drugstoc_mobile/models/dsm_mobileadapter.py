import requests
import werkzeug
import logging
import traceback
import random
import string

from odoo import models, api, service
from odoo.tools.translate import _
from odoo.exceptions import UserError
import datetime
from datetime import timedelta
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, misc

_logger = logging.getLogger(__name__)


class MobileAppAdapter(models.Model):
    _name = 'drugstoc_mobile.mobileadapter'

    @api.model
    def init_paystack(self, inv_id):
        inv = self.env['account.invoice'].sudo().browse(inv_id)
        if inv:
            # Get the payment_gateway config of the rep responsible for this sale\invoice
            gw = inv.user_id.payment_gateway
            if gw and gw.sudo().journal_id:

                # Generate payment reference -> sale order name - invoice number
                pmt_ref = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(6))
                pmt_ref = inv.origin + '-' + inv.number.replace('/', '.') + '-' + pmt_ref

                # Get the authorization url from paystack. send the payment reference
                headers = {
                    'Authorization': 'Bearer ' + gw.sudo().secret,
                    'Content-Type': 'application/json'
                }

                tranx_data = {
                    "email": inv.partner_id.email,
                    "amount": inv.amount_total * 100,
                    "reference": pmt_ref
                }

                _logger.info(tranx_data)

                r = requests.post(gw.sudo().charge_url, json=tranx_data, headers=headers, timeout=65)
                resp = r.json()

                _logger.info(resp)

                if resp['status'] and resp['message'].lower() == "authorization url created":
                    inv.write({'payment_ref': pmt_ref})
                    return {'auth_url': resp['data']['authorization_url']}
                else:
                    raise UserError("Payment gateway processing error.")
            else:
                raise UserError("No gateway configured.")
        else:
            raise UserError("Invoice not found.")

    @api.model
    def cancel_invoice(self, partner_id):
        order = self.env['sale.order'].sudo().browse(partner_id)
        if order:
            order.write({'state': 'cancel'})
            return {'success': True};
        else:
            return {'success': False};

    @api.model
    def create_order(self, products, partner_id, saleorder, location=None, confirm=False, device_info=''):
        partner = self.env['res.partner'].sudo().browse(partner_id)
        if partner:
            # Create Sale Order
            so = self.get_so_default(partner_id)
            so.update(saleorder)
            so = self.env['sale.order'].sudo().create(so)
            so.message_post(body=device_info)
            # _logger.info(so)

            # Create Sale Order Line
            for item in products:
                product = self.get_order_line(item.get('product_id'), item.get('qty'), partner_id)
                _logger.info(product)
                if product:
                    sale_line = self.env['sale.order.line'].sudo().create({
                        'name': product['name'],
                        'product_id': product['product_id'],
                        'price_unit': product['price_total'],
                        'product_uom': product['product_uom'],
                        'tax_id': product['tax_id'],
                        'product_uom_qty': item.get('qty'),
                        'discount': product['discount'],
                        'order_id': so.id
                    })

            # Create Calendar Event
            if location:
                self.create_event({
                    'name': so.name,
                    'display_name': so.name,
                    'start': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'stop': (datetime.datetime.now() + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S"),
                    'location': location,
                    'order_ids': [[so.id]],
                    'partner_ids': [[6, False, [partner_id]]],
                    'reason': 'Sale'
                })

            # Confirm Order
            if confirm:
                so.action_confirm()

            return {'name': so.name, 'id': so.id}

    @api.model
    def get_categories(self):
        fields = ['name']

        return self.do_search_read('product.category', fields, 0, 0, [], "name asc")

    @api.model
    def get_myitems(self, id):
        # Get all orders for the partner_id specified
        orders = self.env['sale.order'].sudo().search(['&', ['partner_id', '=', id], ["state", "in",
                                                                                      ["draft", "sale", "done"]]],
                                                      offset=0, limit=5, order="date_order desc")
        order_lists = []
        if orders:
            _logger.info("Orders Founds")
            for order in orders:
                _logger.info("Order ID#: " + str(order.id))
                for order_line in order.order_line:
                    _logger.info("Order Line ID#: " + str(order.id))
                    product = {
                        "id": order_line.product_id.id,
                        "name": order_line.product_id.name.strip(),
                        "image": order_line.product_id.image_medium.decode('utf-8')
                        if isinstance(order_line.product_id.image_medium,
                                      bytes) else order_line.product_id.image_medium,
                        "price": order_line.product_id.list_price,
                        "available": order_line.product_id.qty_available,
                        "currency": order_line.currency_id.name,
                        "currency_id": order_line.currency_id.id,
                        "description": order_line.product_id.description_sale,
                        "ref": order_line.product_id.default_code,
                        "category": order_line.product_id.categ_id.name,
                        "composition": order_line.product_id.x_studio_field_5Gttm
                    }
                    if not self.check_exist(order_lists, product["id"]):
                        _logger.info(product)
                        order_lists.append(product)
        else:
            _logger.info("No Orders Founds")

        return order_lists

    def check_exist(self, product_list, id):
        for product in product_list:
            if product["id"] == id:
                return True
            return False

    @api.model
    def create_event(self, data):
        _logger.info(data)
        evt = self.env['calendar.event'].sudo().create(data)
        evt.update({
            'user_id': self.env.uid
        })
        return {'name': evt.name, 'id': evt.id}

    @api.model
    def get_price_lists(self, id):
        # Get all Price Lists for the company specified
        price_lists = self.env['product.pricelist'].sudo().search([['active', '=', True]],
                                                                  offset=0, limit=0, order="name asc")

        pl_list = []
        for pl in price_lists:
            pl_list.append({
                'id': pl.id,
                'name': pl.name
            })

        return pl_list

    def getDefSO(self):
        sale_pool = self.env['sale.order']
        defSO = sale_pool.sudo().default_get(
            [
                "state",
                "picking_ids",
                "delivery_count",
                "invoice_count",
                "name",
                "partner_id",
                "partner_invoice_id",
                "partner_shipping_id",
                "validity_date",
                "confirmation_date",
                "pricelist_id",
                "currency_id",
                "payment_term_id",
                "order_line",
                "amount_untaxed",
                "amount_tax",
                "amount_total",
                "note",
                "warehouse_id",
                "incoterm",
                "picking_policy",
                "user_id",
                "team_id",
                "client_order_ref",
                "company_id",
                "analytic_account_id",
                "date_order",
                "fiscal_position_id",
                "invoice_status",
                "origin",
                "message_follower_ids",
                "activity_ids",
                "message_ids"
            ]
        )
        return defSO

    def getDefSOL(self):
        sale_line_pool = self.env['sale.order.line']
        # Default Get SOL
        defSOL = sale_line_pool.sudo().default_get([
            "sequence",
            "product_updatable",
            "product_id",
            "layout_category_id",
            "name",
            "product_uom_qty",
            "qty_delivered",
            "qty_invoiced",
            "qty_to_invoice",
            "product_uom",
            "analytic_tag_ids",
            "route_id",
            "price_unit",
            "tax_id",
            "discount",
            "price_subtotal",
            "price_total",
            "qty_delivered_updateable",
            "state",
            "invoice_status",
            "customer_lead",
            "currency_id"
        ])
        return defSOL

    @api.model
    def get_so_default(self, partner_id):
        # _logger.info('Partner: ' + str(partner_id))
        partner = self.env["res.partner"].sudo().browse(partner_id)
        # logging.info(partner)
        if partner:
            so = self.getDefSO()
            so.update({
                'partner_id': partner.id,
                'pricelist_id': partner.property_product_pricelist.id,
                'payment_term_id': self.sale_get_payment_term(partner).id,
                'partner_invoice_id': partner.id,
                'partner_shipping_id': partner.id,
                'user_id': self.env.uid,
                'company_id': partner.company_id.id,
                'currency_id': partner.currency_id.id
            })
            # logging.info(so)
            return so
        else:
            return []

    @api.model
    def get_products(self, id, category=None, product=None):
        if category:
            domain = ['&', ['company_id', '=', id], ["sale_ok", "=", True], ["website_published", "=", True],
                      ['categ_id', "=", category]]
        else:
            domain = ['&', ['company_id', '=', id], ["sale_ok", "=", True], ["website_published", "=", True]]

        if product:
            domain.append(['name', 'like', product])

        # Get all products for the company specified
        products = self.env['product.product'].sudo().search(domain, offset=0, limit=0, order="name asc")

        prod = []
        for product in products:
            prod.append({
                'id': product.id,
                'name': product.name.strip(),
                'image': product.image_medium.decode('utf-8') if isinstance(product.image_medium,
                                                                            bytes) else product.image_medium,
                'price': product.list_price,
                'available': product.qty_available,
                'currency': product.currency_id.name,
                'currency_id': product.currency_id.id,
                'description': product.description_sale,
                # 'taxes': self.getTaxes(product.taxes_id),
                # 'uom_id': product.uom_id.id,
                'ref': product.default_code,
                'category': product.categ_id.name,
                'composition': product.x_studio_field_5Gttm
            })
        return prod

    @api.model
    def get_customers(self, id):
        # Get all customers for the specified company and user.
        customers = self.env['res.partner'].sudo().search(
            ['&', ['company_id', '=', id], ['customer', '=', True], ["is_company", "=", True],
             ["user_id", "=", self.env.uid]], offset=0, limit=0, order="name asc")

        customer_list = []
        for customer in customers:
            customer_list.append({
                'id': customer.id,
                'name': customer.name.strip(),
                'image': customer.image_medium.decode('utf-8') if isinstance(customer.image_medium,
                                                                             bytes) else customer.image_medium,
                'email': customer.email,
                'sale_orders': self.getSaleOrders(customer.sale_order_ids),
                'pricelist': customer.property_product_pricelist,
                'currency': customer.company_id.currency_id.name,
                'company': customer.company_id.id
            })

        return customer_list

    @api.model
    def get_customer(self, id, mini=None):
        # Get customer with the specified ID
        customer = self.env['res.partner'].sudo().search([['id', '=', id]], offset=0, limit=0, order="name asc")

        if customer:
            cust = {
                "name": customer.name,
                "email": customer.email,
                "mobile": customer.mobile,
                "phone": customer.phone,
                "title": customer.title.name,
                "street": customer.street,
                "street2": customer.street2,
                "city": customer.city,
                "state": customer.state_id.name,
                "function": customer.function,
                "country": customer.country_id.name,
                "zip": customer.zip,
                "website": customer.website,
                'currency': customer.currency_id.name,
                'company': customer.company_id.name
            }

            if not mini:
                cust.update(
                    {"image": customer.image.decode('utf-8') if isinstance(customer.image, bytes) else customer.image})

            return cust
        else:
            return {}

    def getTaxes(self, taxes):
        taxes_list = []
        for tax in taxes:
            taxes_list.append(tax.id)
        return taxes_list

    def getSaleOrders(self, saleorders):
        so_list = []
        for so in saleorders:
            so_list.append(so.id)
        return so_list

    @api.model
    def get_order_line(self, product_id, qty, partner_id):
        sale_line_pool = self.env['sale.order.line']
        product_pool = self.env['product.product']
        product = product_pool.sudo().browse(product_id)
        if product:
            sale_line = self.getDefSOL()
            sale_line.update({
                'order_id': self.get_so_default(partner_id),
                'product_id': product.id,
                'product_uom_qty': qty
            })
            sale_line = sale_line_pool.sudo().new(sale_line)
            sale_line.product_id_change()
            sale_line._onchange_discount()
            sale_line._compute_amount()
            return sale_line._convert_to_write(sale_line._cache)
        else:
            return {}

    @api.model
    def get_profile(self, partner_id, customer=False):
        partner = self.env["res.partner"].sudo().browse(partner_id)
        if partner:
            if customer:
                return {
                    "name": partner.name.strip(),
                    "email": partner.email,
                    "image": partner.image_medium,
                    "title": partner.function,
                    "rep_name": partner.user_id.name.strip(),
                    "rep_email": partner.user_id.email,
                    "rep_image": partner.user_id.image_medium,
                    "rep_phone": partner.user_id.mobile
                }
            else:
                return {
                    "name": partner.name.strip(),
                    "email": partner.email,
                    "image": partner.image_medium,
                    "title": partner.function
                }
        else:
            return {};

    @api.model
    def get_crm_teams(self, id):
        # Get all crm teams for the company specified
        crm_teams = self.env['crm.team'].sudo().search(['&', ['company_id', '=', id], ['active', '=', True]],
                                                       offset=0, limit=0, order="name asc")

        crm_list = []
        for crm_team in crm_teams:
            crm_list.append({
                'id': crm_team.id,
                'name': crm_team.name
            })

        return crm_list

    @api.model
    def get_payment_terms(self, id):
        # Get all payment terms for the company specified
        payment_terms = self.env['account.payment.term'].sudo().search(
            ['&', ['company_id', '=', id], ['active', '=', True]],
            offset=0, limit=0, order="name asc")

        pt_list = []
        for pt in payment_terms:
            pt_list.append({
                'id': pt.id,
                'name': pt.name
            })

        return pt_list

    @api.model
    def get_orders(self, id):
        # Get all orders for the partner_id specified
        orders = self.env['sale.order'].sudo().search(['&', ['partner_id', '=', id], ["state", "in",
                                                                                      ["draft", "sale", "done"]]],
                                                      offset=0, limit=0, order="name asc")
        order_lists = []
        if orders:
            for order in orders:
                order_lists.append({
                    "id": order.id,
                    "name": order.name,
                    "total": order.amount_total,
                    "date_confirmed": order.confirmation_date,
                    "currency": order.currency_id.name,
                    "lines": len(list(order.order_line)),
                    "state": order.state,
                    "salesperson": order.user_id.name,
                    "date_received": order.date_order,
                    "invoice_status": order.invoice_status
                })
            # _logger.warning(type(order.order_line))

        return order_lists

    @api.model
    def get_order_lines(self, id):
        # Get all the order_lines for the order_id specified
        order_lines = self.env['sale.order.line'].sudo().search([['order_id', '=', id]], offset=0, limit=0,
                                                                order="name asc")

        order_lines_list = []
        if order_lines:
            for order_line in order_lines:
                order_lines_list.append({
                    "id": order_line.id,
                    "product_id": order_line.product_id.id,
                    "name": order_line.product_id.name,
                    "image": order_line.product_image.decode('utf-8') if isinstance(order_line.product_image,
                                                                                    bytes) else order_line.product_image,
                    "price": order_line.price_unit,
                    "qty": order_line.product_uom_qty,
                    "total": order_line.price_total,
                    "currency": order_line.currency_id.name,
                    "qty_available": order_line.product_id.qty_available
                })
                # _logger.warning(prod)
        return order_lines_list

    @api.model
    def get_invoices(self, id):
        # Get all invoices for the partner_id specified
        invoices = self.env['account.invoice'].sudo().search(['&', ['partner_id', '=', id], ["state", "in",
                                                                                             ["draft", "paid",
                                                                                              "open"]]], offset=0,
                                                             limit=0, order="date_invoice desc")

        invoice_list = []
        for invoice in invoices:
            invoice_list.append({
                "id": invoice.id,
                "number": invoice.number if invoice.number else '',
                "total": invoice.amount_total,
                "date_invoice": invoice.date_invoice,
                "date_due": invoice.date_due,
                "lines": len(list(invoice.invoice_line_ids)),
                "currency": invoice.currency_id.name,
                "state": invoice.state,
                "salesperson": invoice.user_id.name,
                "origin": invoice.origin
            })
            # _logger.warning(type(order.order_line))
        return invoice_list

    @api.model
    def get_invoice_lines(self, id):
        # Get all the invoice_lines for the invoice_id specified
        invoice_lines = self.env['account.invoice.line'].sudo().search([['invoice_id', '=', id]], offset=0, limit=0,
                                                                       order="name asc")
        invoice_lines_list = []
        if invoice_lines:
            for invoice_line in invoice_lines:
                invoice_lines_list.append({
                    "id": invoice_line.id,
                    "name": invoice_line.product_id.name,
                    "image": invoice_line.product_image.decode('utf-8') if isinstance(invoice_line.product_image,
                                                                                      bytes) else invoice_line.product_image,
                    "price": invoice_line.price_unit,
                    "qty": invoice_line.quantity,
                    "total": invoice_line.price_total,
                    "currency": invoice_line.currency_id.name,
                })
                # _logger.warning(prod)

        return invoice_lines_list

    @api.model
    def get_events(self, start):
        fields = ['name', 'duration', 'start', 'reason']

        return self.do_search_read('calendar.event', fields, 0, 0,
                                   ['&', ['user_id', '=', self.env.uid], ["start", "=like", start]], "name asc")

    @api.model
    def sale_get_payment_term(self, partner):
        return (
                partner.property_payment_term_id or
                self.env.ref('account.account_payment_term_immediate', False) or
                self.env['account.payment.term'].sudo().search([('company_id', '=', partner.company_id.id)], offset=0,
                                                               limit=1))

    def do_search_read(self, model, fields=False, offset=0, limit=False, domain=None
                       , sort=None):
        """ Performs a search() followed by a read() (if needed) using the
        provided search criteria

        :param str model: the name of the model to search on
        :param fields: a list of the fields to return in the result records
        :type fields: [str]
        :param int offset: from which index should the results start being returned
        :param int limit: the maximum number of records to return
        :param list domain: the search domain for the query
        :param list sort: sorting directives
        :returns: A structure (dict) with two keys: ids (all the ids matching
                  the (domain, context) pair) and records (paginated records
                  matching fields selection set)
        :rtype: list
        """
        Model = self.env[model]

        records = Model.search_read(domain, fields, offset=offset or 0, limit=limit or False, order=sort or False)

        if not records:
            return {
                'length': 0,
                'records': []
            }
        if limit and len(records) == limit:
            length = Model.search_count(domain)
        else:
            length = len(records) + (offset or 0)
        return {
            'length': length,
            'records': records
        }

    @api.model
    def validate_invoice(self, id):
        invoice = self.env['account.invoice'].sudo().browse(id)
        return invoice.action_invoice_open()

    @api.model
    def pay_invoice(self, inv_id, pmtRef):
        inv = self.env['account.invoice'].sudo().browse(inv_id)
        if inv:
            user = self.env['res.users'].sudo().browse(self.env.uid)
            return inv.pay_and_reconcile(user.payment_gateway.journal_id)
        else:
            raise UserError("Invoice not found.")

    @api.model
    def confirm_sale_order(self, id):
        so = self.env['sale.order'].sudo().browse(id)
        return so.action_confirm()

    @api.model
    def cancel_sale_order(self, id):
        so = self.env['sale.order'].sudo().browse(id)
        return so.action_cancel()

    @api.model
    def invoice_order(self, id):
        invoice = self.env['sale.advance.payment.inv'].sudo()
        tmp_inv = invoice.default_get([
            "count",
            "advance_payment_method",
            "product_id",
            "amount",
            "deposit_account_id",
            "deposit_taxes_id"
        ])
        ctx = {
            "active_model": "sale.order",
            "active_id": id,
            "active_ids": [
                id
            ]
        }
        inv = invoice.with_context(ctx).create(tmp_inv)
        return inv.create_invoices()
