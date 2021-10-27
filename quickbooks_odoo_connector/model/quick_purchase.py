# -*- coding: utf-8 -*-
#
#
#    TechSpawn Solutions Pvt. Ltd.
#    Copyright (C) 2016-TODAY TechSpawn(<http://www.techspawn.com>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
import logging
import time

from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import Warning
from requests_oauthlib import OAuth2Session
from ..unit.quick_purchase_exporter import QboPurchaseExport

_logger = logging.getLogger(__name__)

class quickbook_purchase_order(models.Model):
    _inherit = 'purchase.order'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='Quick Backend', store=True,
                                 readonly=False, required=False,
                                 )
    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)
    sync_date = fields.Datetime(string='Last synchronization date')
    location_id = fields.Many2one('stock.location', 'Destination', required=False)
    pricelist_id = fields.Many2one('product.pricelist', 'Pricelist', required=False)
    doc_number = fields.Char(string='QBO Doc Number', help='Stores QBO document number for reference purpose')

    def get_ids(self, arguments, backend_id, filters, record_id):
        # arguments = 'purchase'
        backend = self.backend_id.browse(backend_id)
        headeroauth = OAuth2Session(backend.client_key)
        headers = {'Authorization': 'Bearer %s' % backend.access_token, 'content-type': 'application/json',
                   'accept': 'application/json'}
        method = '/query?query=select%20ID%20from%20'
        if not record_id:
            data = headeroauth.get(backend.location + backend.company_id +
                                   method + arguments + '%20STARTPOSITION%20' + str(
                filters['count']) + '%20MAXRESULTS%20' + str(300) + '&minorversion=4', headers=headers)
        else:
            data = headeroauth.get(backend.location + backend.company_id +
                                   '/' + arguments + '/' + str(record_id) + '?minorversion=4', headers=headers)
            if data.status_code == 429:
                self.env.cr.commit()
                time.sleep(60)
                data = headeroauth.get(backend.location + backend.company_id +
                                   '/' + arguments + '/' + str(record_id) + '?minorversion=4', headers=headers)

        if data:
            if isinstance(arguments, list):
                while arguments and arguments[-1] is None:
                    arguments.pop()
            start = datetime.now()
            try:
                if 'false' or 'true' or 'null' in data.content:
                    # converting str data contents to bytes
                    data1 = bytes(data.content)
                    # decoding data contents
                    data_decode = data.content.decode('utf-8')
                    # encoding data contents
                    result = data_decode.replace('false', 'False').encode('utf-8')

                    data_decode_one = result.decode('utf-8')
                    result = data_decode_one.replace('true', 'True').encode('utf-8')

                    data_decode_two = result.decode('utf-8')
                    result = data_decode_two.replace('null', 'False')

                    result = eval(result)
                else:
                    result = eval(data.content)
            except:
                _logger.error("api.call(%s, %s) failed", method, arguments)
            else:
                _logger.debug("api.call(%s, %s) returned %s in %s seconds",
                              method, arguments, result,
                              (datetime.now() - start).seconds)
            return result

    def purchase_import_mapper(self, backend_id, data):
        record = data
        _logger.info("API DATA :%s", data)
        if 'PurchaseOrder' in record:
            rec = record['PurchaseOrder']
            if 'VendorRef' in rec:
                partner_id = self.env['res.partner'].search(
                    [('supplier_rank', '>', 0), ('quickbook_id', '=', rec['VendorRef']['value'])])

                for x in partner_id:
                    partner_id = x.id or False
            else:
                partner_id = False

            product_ids = []
            if 'Line' in rec:
                for lines in rec['Line']:
                    if 'ItemBasedExpenseLineDetail' in lines:
                        product_template_id = self.env['product.template'].search(
                            [('quickbook_id', '=', lines['ItemBasedExpenseLineDetail']['ItemRef']['value'])])
                        product_id = self.env['product.product'].search([('name', '=', product_template_id.name)])
                        order_id = self.env['purchase.order'].search(
                            [('backend_id', '=', backend_id), ('quickbook_id', '=', rec['Id'])])

                        order = self.env['purchase.order.line'].search(
                            [('order_id', '=', order_id.id), ('quickbook_id', '=', lines['Id']),
                             ('name', '=', lines['Description'])])
                        result = {'product_id': product_id.id,
                                  'price_unit': lines['ItemBasedExpenseLineDetail']['UnitPrice'],
                                  'product_qty': lines['ItemBasedExpenseLineDetail']['Qty'],
                                  'product_uom': 1,
                                  'price_subtotal': lines['Amount'],
                                  'name': lines.get('Description'),
                                  'quickbook_id': lines['Id'],
                                  'date_planned': rec['TxnDate']
                                  }
                        if not order:
                            product_ids.append([0, 0, result]) or False
                        else:
                            product_ids.append([1, order.id, result])
            if rec['TotalAmt']:
                amount_total = rec['TotalAmt']
            if rec['POStatus']:
                if rec['POStatus'] == 'Open':
                    status = 'draft'
                elif rec['POStatus'] == 'Closed':
                    status = 'done'
                else:
                    status = 'Open'
            if rec['Id']:
                quickbook_id = rec['Id']

            if 'CurrencyRef' in rec.keys():
                currency = self.env['res.currency'].search([('name', '=', rec['CurrencyRef'].get('value'))]).id

        purchase_id = self.env['purchase.order'].search([('quickbook_id', '=', quickbook_id),
                                                         ('backend_id', '=', backend_id)])
        vals = {
            'partner_id': partner_id,
            'date_order': rec['TxnDate'],
            'doc_number': rec.get('DocNumber') if 'DocNumber' in rec.keys() else '',
            'amount_total': rec['TotalAmt'],
            'state': status,
            'order_line': product_ids,
            'quickbook_id': quickbook_id,
            'backend_id': backend_id,
            'currency_id': currency,
        }

        if not purchase_id:
            try:
                purchase = super(quickbook_purchase_order, self).create(vals)
                purchase.button_confirm()
                return purchase
            except:
                raise Warning(_("Issue while importing Purchase " + vals.get('doc_number') + ". Please check if there are any missing values in Quickbooks. If no, then please make sure other dependent fields have been imported first."))
        else:
            purchase_id = purchase_id.write(vals)
            return purchase_id

    def purchase_import_batch(self, model_name, backend_id, filters=None):
        """ Import purchase Details. """
        arguments = 'purchaseorder'
        count = 1
        record_ids = ['start']
        filters['url'] = 'purchaseorder'
        filters['count'] = count
        record_ids = self.get_ids(arguments, backend_id, filters, record_id=False)

        if record_ids:
            if 'PurchaseOrder' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['PurchaseOrder']
                for record_id in record_ids:
                    self.env['purchase.order'].importer(arguments=arguments, backend_id=backend_id,
                                                                     filters=filters, record_id=int(record_id['Id']))
            else:
                record_ids = record_ids['QueryResponse']

    def importer(self, arguments, backend_id, filters, record_id):
        data = self.get_ids(arguments, backend_id, filters, record_id)
        if data:
            self.purchase_import_mapper(backend_id, data)

    def sync_purchase(self):
        for backend in self.backend_id:
            self.export_purchase_data(backend)
        return

    def export_purchase_data(self, backend):
        """ export purchase details, save username and create or update backend mapper """
        if not self.backend_id:
            return
        mapper = self.env['purchase.order'].search(
            [('backend_id', '=', backend.id), ('quickbook_id', '=', self.quickbook_id)], limit=1)
        method = 'purchaseorder'
        arguments = [mapper.quickbook_id or None, self]
        export = QboPurchaseExport(backend)
        res = export.export_purchase_order(method, arguments)

        if mapper.id == self.id and self.quickbook_id:
            if mapper and (res['status'] == 200 or res['status'] == 201):
                mapper.write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['PurchaseOrder']['Id']})
                response = res['data']
                count = 0
                for lines in response['PurchaseOrder']['Line']:
                    if 'Id' in lines:
                        order_lines = arguments[1].order_line
                        order_lines[count].write({'quickbook_id': lines['Id']})
                        count += 1
            elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['PurchaseOrder']['Id']})
                response = res['data']
                count = 0
                for lines in response['PurchaseOrder']['Line']:
                    if 'Id' in lines:
                        order_lines = arguments[1].order_line
                        order_lines[count].write({'quickbook_id': lines['Id']})
                        count += 1
        elif (res['status'] == 200 or res['status'] == 201):
            arguments[1].write(
                {'backend_id': backend.id, 'quickbook_id': res['data']['PurchaseOrder']['Id']})
            response = res['data']
            count = 0
            for lines in response['PurchaseOrder']['Line']:
                if 'Id' in lines:
                    order_lines = arguments[1].order_line
                    order_lines[count].write({'quickbook_id': lines['Id']})
                    count += 1

        if res['status'] == 500 or res['status'] == 400:
            for errors in res['errors']['Fault']['Error']:
                msg = errors['Message']
                code = errors['code']
                name = res['name']
                details = 'Message: ' + msg + '\n' + 'Code: ' + code + '\n' + 'Name: ' + str(name.name) + '\n' + 'Detail: ' + \
                          errors['Detail']
                if errors['code']:
                    raise Warning(details)

    @api.model
    def default_get(self, fields):
        res = super(quickbook_purchase_order, self).default_get(fields)
        ids = self.env['qb.backend'].search([]).id
        res['backend_id'] = ids
        return res


class quickbook_purchase_order_line(models.Model):
    _inherit = 'purchase.order.line'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='quick Backend', store=True,
                                 readonly=False, required=False,
                                 )

    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)
    sync_date = fields.Datetime(string='Last synchronization date')