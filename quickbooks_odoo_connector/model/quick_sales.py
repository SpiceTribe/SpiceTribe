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
from odoo.exceptions import except_orm, Warning, RedirectWarning
from odoo import models, fields, api, _
from requests_oauthlib import OAuth2Session
from ..unit.quick_sale_order_exporter import QboSalesOrderExport

_logger = logging.getLogger(__name__)

class quickbook_sale_order(models.Model):

    _inherit = 'sale.order'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='Quick Backend', store=True,
                                 readonly=False, required=False,
                                 )
    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)
    sync_date = fields.Datetime(string='Last synchronization date')
    
    def get_ids(self, arguments, backend_id, filters, record_id):
        # arguments = 'customer'
        backend = self.backend_id.browse(backend_id)
        headeroauth = OAuth2Session(backend.client_key)
        headers = {'Authorization': 'Bearer %s' %backend.access_token, 'content-type': 'application/json', 'accept': 'application/json'}
        method = '/query?query=select%20ID%20from%20'
        if not record_id:
            data = headeroauth.get(backend.location+backend.company_id +
                                        method+arguments+'%20STARTPOSITION%20'+str(filters['count'])+'%20MAXRESULTS%20' + str(300)+'&minorversion=4', headers=headers)
        else:
            data = headeroauth.get(backend.location+backend.company_id +
                                    '/'+arguments+'/'+str(record_id)+'?minorversion=4', headers=headers)
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
                if 'false' or 'true' or 'null'in data.content:
                    # converting str data contents to bytes
                    data1 = bytes(data.content)
                    # decoding data contents
                    data_decode = data.content.decode('utf-8')
                    # encoding data contents
                    result = data_decode.replace('false','False').encode('utf-8')

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

    def sale_import_mapper(self, backend_id, data):
        record = data
        _logger.info("API DATA :%s", data)
        if 'SalesReceipt' in record:
            rec = record['SalesReceipt']
            if 'CustomerRef' in rec:
                partner_id = self.env['res.partner'].search(
                    [('customer_rank', '>', 0),('quickbook_id', '=', rec['CustomerRef']['value'])])

                partner_id = partner_id.id or False
            else:
                partner_id = False

            if 'Line' in rec:
                product_ids = []
                for lines in rec['Line']:
                    if 'SalesItemLineDetail' in lines:
                        product_template_id = self.env['product.template'].search(
                            [('quickbook_id', '=', lines['SalesItemLineDetail']['ItemRef']['value']),
                             ('name', '=', lines['SalesItemLineDetail']['ItemRef']['name'])])
                        product_id = self.env['product.product'].search([('name', '=', product_template_id.name)])
                        
                        order_id = self.env['sale.order'].search([('backend_id', '=', backend_id),('quickbook_id', '=', rec['Id'])])                       
                        tax_id = []
                        
                        if not self.env.company.partner_id.country_id.code is 'US':
                            if 'TaxCodeRef' in lines.get('SalesItemLineDetail'):
                                taxs_id = self.env['account.tax'].search([('amount_type', '=', 'group'),('quickbook_id', '=', lines['SalesItemLineDetail']['TaxCodeRef']['value'])]).id
                                if taxs_id:
                                    tax_id.append(taxs_id)
                        else:
                            if lines['SalesItemLineDetail']['TaxCodeRef']['value'] == 'TAX':
                                if 'TxnTaxDetail' in rec and 'TxnTaxCodeRef' in rec.get('TxnTaxDetail'):
                                    tax_id = self.env['account.tax'].search([('amount_type', '=', 'group'),('quickbook_id', '=', rec['TxnTaxDetail']['TxnTaxCodeRef']['value'])]).ids or []

                        order = self.env['sale.order.line'].search([('order_id', '=', order_id.id),('quickbook_id', '=', lines['Id'])])

                        result = {'product_id':product_id.id,
                            'sequence': lines['LineNum'],
                            'price_unit': lines['SalesItemLineDetail']['UnitPrice'],
                            'product_uom_qty': lines['SalesItemLineDetail']['Qty'],
                            'tax_id': [(6, 0, tax_id)],
                            'product_uom': 1,
                            'price_subtotal': lines['Amount'],
                            'name': lines.get('Description'),
                            'quickbook_id': lines['Id'],
                            }
                        if not order:
                            product_ids.append([0,0,result]) or False
                        else:
                            product_ids.append([1,order.id,result])

            if rec['Id']:
                quickbook_id = rec['Id']

            if 'CurrencyRef' in rec.keys():
                price_list = self.env['product.pricelist'].search([('currency_id.name', '=', rec['CurrencyRef'].get('value'))], limit=1).id
                if not price_list:
                    raise Warning('Create Pricelist of Currency' + str(rec['CurrencyRef'].get('value')) + ' - ' + str(rec['CurrencyRef'].get('name')))

        order_id = self.env['sale.order'].search([('quickbook_id', '=', quickbook_id),
                          ('backend_id', '=', backend_id)])
        vals= {
        'partner_id': partner_id,
        'date_order': rec['TxnDate'],
        'client_order_ref': rec.get('DocNumber') if 'DocNumber' in rec.keys() else '',
        'order_line': product_ids,
        'quickbook_id': quickbook_id,
        'backend_id': backend_id,
        'pricelist_id': price_list,
        }
        if not order_id:
            try:
                order = super(quickbook_sale_order, self).create(vals)
                order.action_confirm()
                return order
            except:
                raise Warning(_("Issue while importing Sale Receipt " + vals.get('client_order_ref') + ". Please check if there are any missing values in Quickbooks. If no, then please make sure other dependent fields have been imported first."))    
        else:
            order = order_id.write(vals)
            return order

    def sale_import_batch(self, model_name, backend_id, filters=None):
        """ Import Sales Details. """
        arguments = 'salesreceipt'
        count = 1
        record_ids = ['start']
        filters['url'] = 'salesreceipt'
        filters['count'] = count
        record_ids = self.get_ids(arguments, backend_id, filters, record_id=False)

        if record_ids:
            if 'SalesReceipt' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['SalesReceipt']
                for record_id in record_ids:
                    self.env['sale.order'].importer(arguments=arguments, backend_id=backend_id, filters=filters, record_id=int(record_id['Id']))
            else:
                record_ids = record_ids['QueryResponse']

    def importer(self, arguments, backend_id, filters, record_id):
        data = self.get_ids(arguments, backend_id, filters, record_id)
        if data:
            self.sale_import_mapper(backend_id, data)

    def sync_sale(self):
        for backend in self.backend_id:
            self.export_sale_data(backend)
        return

    def export_sale_data(self, backend):
        """ export customer details, save username and create or update backend mapper """
        if not self.backend_id:
            return
        mapper = self.env['sale.order'].search(
            [('backend_id', '=', backend.id), ('quickbook_id', '=', self.quickbook_id)], limit=1)
        method = 'salesreceipt'
        arguments = [mapper.quickbook_id or None, self]
        export = QboSalesOrderExport(backend)
        res = export.export_sales_receipt(method, arguments)

        if mapper.id == self.id and self.quickbook_id:
            if mapper and (res['status'] == 200 or res['status'] == 201):
                mapper.write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['SalesReceipt']['Id']})
                response = res['data']
                count = 0
                for lines in response['SalesReceipt']['Line']:
                    if 'Id' in lines:
                        order_lines = arguments[1].order_line
                        order_lines[count].write({'sequence': lines['LineNum'], 'quickbook_id': lines['Id']})
                        count += 1
            elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['SalesReceipt']['Id']})
                response = res['data']
                count = 0
                for lines in response['SalesReceipt']['Line']:
                    if 'Id' in lines:
                        order_lines = arguments[1].order_line
                        order_lines[count].write({'sequence': lines['LineNum'], 'quickbook_id': lines['Id']})
                        count += 1
        elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['SalesReceipt']['Id']})
                response = res['data']
                count = 0
                for lines in response['SalesReceipt']['Line']:
                    if 'Id' in lines:
                        order_lines = arguments[1].order_line
                        order_lines[count].write({'sequence': lines['LineNum'], 'quickbook_id': lines['Id']})
                        count += 1
        
        if res['status'] == 500 or res['status'] == 400:
            for errors in res['errors']['Fault']['Error']:
                msg = errors['Message']
                code = errors['code']
                name = res['name']
                details = 'Message: ' + msg + '\n' + 'Code: ' + code + '\n' + 'Name: '+ str(name.name) + '\n' + 'Detail: ' + errors['Detail']
                if errors['code']:
                    raise Warning(details)

    @api.model
    def default_get(self,fields):
        res=super(quickbook_sale_order,self).default_get(fields)
        ids=self.env['qb.backend'].search([]).id
        res['backend_id']=ids
        return res


class quickbook_sale_order_line(models.Model):

    _inherit = 'sale.order.line'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='quick Backend', store=True,
                                 readonly=False, required=False,
                                 )

    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)
    sync_date = fields.Datetime(string='Last synchronization date')