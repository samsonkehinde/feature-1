
# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class DSM_CalendarEvent(models.Model):
    _inherit = "calendar.event"

    reason = fields.Text(string='Reason', help='Reason for the Visit')
    order_ids = fields.One2many(string='Transactions', comodel_name='sale.order', inverse_name='event_id')

class DSM_SaleOrder(models.Model):
    _inherit = "sale.order"

    event_id = fields.Many2one(string='Calendar Event', comodel_name='calendar.event')
