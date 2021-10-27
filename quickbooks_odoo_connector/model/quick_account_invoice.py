import logging
import time
import odoo.addons.decimal_precision as dp

from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import Warning, RedirectWarning
from requests_oauthlib import OAuth2Session
from ..unit.quick_invoice_exporter import QboInvoiceExport

_logger = logging.getLogger(__name__)

class account_invoice(models.Model):

    _inherit = 'account.move'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='Quick Backend', store=True,
                                 readonly=False, required=False,
                                 )

    quickbook_id = fields.Char(
        string='ID on Woo', readonly=False, required=False)
    sync_date = fields.Datetime(string='Last synchronization date')
    doc_number = fields.Char(string='QBO Doc Number', help='Stores QBO document number for reference purpose')

    @api.model
    def create(self, vals):
        return super(account_invoice, self).create(vals)

    def get_ids(self, arguments, backend_id, filters, record_id):
        backend = self.backend_id.browse(backend_id)
        headeroauth = OAuth2Session(backend.client_key)
        headers = {'Authorization': 'Bearer %s' %backend.access_token, 'content-type': 'application/json', 'accept': 'application/json'}
        method = '/query?query=select%20ID%20from%20'
        if not record_id:
            data = headeroauth.get(backend.location + backend.company_id +
                                        method + arguments + '%20STARTPOSITION%20' + str(filters['count']) + '%20MAXRESULTS%20' + str(300) + '&minorversion=4', headers=headers)
        else:
            data = headeroauth.get(backend.location + backend.company_id +
                                    '/' + arguments + '/' + str(record_id) + '?minorversion=4', headers=headers)
            if data.status_code == 429:
                self.env.cr.commit()
                time.sleep(60)
                data = headeroauth.get(backend.loaction + backend.company_id + '/' + arguments + str(record_id) + '?minorversion=4', headers=headers)

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

    def invoice_import_mapper(self, backend_id, data):
        record = data
        _logger.info("API DATA :%s", data)
        if 'Invoice' in record:
            rec = record['Invoice']
            inv_type = 'out_invoice'
            if 'CustomerRef' in rec:
                partner_id = self.env['res.partner'].search(
                    [('quickbook_id', '=', rec['CustomerRef']['value']),
                     ('name', '=', rec['CustomerRef']['name'])])
                if not partner_id:
                    raise Warning(('Please import "Customer" First'))

                account_id = partner_id.property_account_receivable_id.id or None
                partner_id = partner_id.id or False
            else:
                partner_id = False
                account_id = None
            
            if 'DocNumber' in rec:
                doc_number =  rec['DocNumber']
            else:
                doc_number = None
            if 'DueDate' in record['Invoice']:
                date_due = rec['DueDate']
            else:
                date_due = None

            if 'SalesTermRef' in rec:
                payment_term = self.env['account.payment.term'].search(
                    [('quickbook_id', '=', rec['SalesTermRef']['value'])])

                payment_term = payment_term.id
            else:
                payment_term = False

            if 'TxnDate' in rec:
                date_invoice = rec['TxnDate']
            else:
                date_invoice = None
           
            product_ids = []
            if 'Line' in rec:
                for lines in rec['Line']:
                    if 'SalesItemLineDetail' in lines:
                        product_template_id = self.env['product.template'].search(
                            [('quickbook_id', '=', lines['SalesItemLineDetail']['ItemRef']['value']),
                             ('name', '=', lines['SalesItemLineDetail']['ItemRef']['name'])])
                        product_id = self.env['product.product'].search([('product_tmpl_id', '=', product_template_id.id),
                             ('name', '=', product_template_id.name)])
                        order_id = self.env['account.move'].search([('backend_id', '=', backend_id),('quickbook_id', '=', rec['Id'])])

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
                        
                        order = self.env['account.move.line'].search([('move_id', '=', order_id.id),('quickbook_id', '=', lines['Id']),('name', '=', lines.get('Description'))])
                        
                        if 'UnitPrice' in lines['SalesItemLineDetail']:
                            unitprice = lines['SalesItemLineDetail']['UnitPrice']
                        else:
                            unitprice = product_id.list_price

                        if 'Qty' in lines['SalesItemLineDetail']:
                            quantity = lines['SalesItemLineDetail']['Qty']
                        else:
                            quantity = product_id.qty_available
                        try:
                            name = lines['Description']
                        except KeyError:
                            name = lines['SalesItemLineDetail']['ItemRef']['name']
                        result = {'product_id':product_id.id,
                            'price_unit': unitprice,
                            'quantity': quantity,
                            'tax_line_id': [(6, 0, tax_id)],
                            'account_id': product_id.property_account_income_id.id or None,
                            'product_uom_id': 1,
                            'price_subtotal': lines['Amount'],
                            'name': name,
                            'quickbook_id': lines['Id'],
                            }
                        if not order:
                            product_ids.append([0,0,result]) or False
                        else:
                            product_ids.append([1,order.id,result])
            tax_lines = []
            if 'TxnTaxDetail' in rec:
                rec_t = record['Invoice'].get('TxnTaxDetail')
                if 'TaxLine' in rec_t:
                    for line in rec_t.get('TaxLine'):
                        line_tax = line['TaxLineDetail'].get('TaxRateRef')
                        tax_id = self.env['account.tax'].search([('amount_type', '!=', 'group'),('rate_quickbook_id', '=', line_tax.get('value'))])
                        order_id = self.env['account.move'].search([('backend_id', '=', backend_id),('quickbook_id', '=', record['Invoice']['Id'])])
                        
                        result = {
                                'name':tax_id.name,
                                'tax_id':tax_id.id or None,
                                'amount':line['Amount'],
                                'manual': False,
                                'company_id':tax_id.company_id.id or None,
                                'currency_id':tax_id.company_id.currency_id.id or None,
                                'base':line['TaxLineDetail'].get('NetAmountTaxable'),
                                }

            if rec['Id']:
                quickbook_id = rec['Id']

            if 'CurrencyRef' in rec.keys():
                currency = self.env['res.currency'].search([('name', '=', rec['CurrencyRef'].get('value'))]).id

        elif 'Bill' in record:
            rec = record['Bill']
            inv_type = 'in_invoice'
            if 'VendorRef' in rec:
                partner_id = self.env['res.partner'].search(
                    [('quickbook_id', '=', rec['VendorRef']['value']),
                     ('name', '=', rec['VendorRef']['name'])])
                if not partner_id:
                    raise Warning(('Please import "Vendor Ref" First'))
                account_id = partner_id.property_account_payable_id.id or None
                for x in partner_id:
                    partner_id = x.id or False
            else:
                partner_id = False
                account_id = None
            
            if 'SalesTermRef' in rec:
                payment_term = self.env['account.payment.term'].search(
                    [('quickbook_id', '=', rec['SalesTermRef']['value'])])
                payment_term = payment_term.id
            else:
                payment_term = False
            
            if 'DocNumber' in rec:
                doc_number =  rec['DocNumber']
            else:
                doc_number = None
            
            if 'DueDate' in rec:
                date_due = rec['DueDate']
            else:
                date_due = None
            
            if 'TxnDate' in rec:
                date_invoice = rec['TxnDate']
            else:
                date_invoice = None
            
            product_ids = []
            if 'Line' in rec:
                for lines in rec['Line']:
                    if 'ItemBasedExpenseLineDetail' in lines:
                        product_template_id = self.env['product.template'].search(
                            [('quickbook_id', '=', lines['ItemBasedExpenseLineDetail']['ItemRef']['value']),
                             ('name', '=', lines['ItemBasedExpenseLineDetail']['ItemRef']['name'])])
                        product_id = self.env['product.product'].search([('product_tmpl_id', '=', product_template_id.id),
                             ('name', '=', product_template_id.name)])
                        order_id = self.env['account.move'].search([('backend_id', '=', backend_id),('quickbook_id', '=', rec['Id'])])

                        tax_id = []
                        if lines['ItemBasedExpenseLineDetail']['TaxCodeRef']['value'] == 'TAX':
                            if 'TxnTaxDetail' in rec and 'TxnTaxCodeRef' in rec.get('TxnTaxDetail'):
                                tax_id = [self.env['account.tax'].search([('amount_type', '=', 'group'),('quickbook_id', '=', rec['TxnTaxDetail']['TxnTaxCodeRef']['value'])]).id]                        
                        order = self.env['account.move.line'].search([('move_id', '=', order_id.id),('quickbook_id', '=', lines['Id']),('name', '=', lines.get('Description'))])
                        
                        if 'UnitPrice' in lines['ItemBasedExpenseLineDetail']:
                            unitprice = lines['ItemBasedExpenseLineDetail']['UnitPrice']
                        else:
                            unitprice = product_id.list_price

                        if 'Qty' in lines['ItemBasedExpenseLineDetail']:
                            quantity = lines['ItemBasedExpenseLineDetail']['Qty']
                        else:
                            quantity = product_id.qty_available
                        result = {'product_id':product_id.id,
                            'price_unit': unitprice,
                            'quantity': quantity,
                            'tax_line_id': [(6, 0, tax_id)],
                            'account_id': product_id.property_account_expense_id.id or None,
                            'product_uom_id': 1,
                            'price_subtotal': lines['Amount'],
                            'name': lines.get('Description'),
                            'quickbook_id': lines['Id'],
                            }
                        if not order:

                            product_ids.append([0,0,result]) or False
                        else:
                            product_ids.append([1,order.id,result])
                    elif 'AccountBasedExpenseLineDetail' in lines:
                        product_account_id = self.env['account.account'].search(
                            [('quickbook_id', '=', lines['AccountBasedExpenseLineDetail']['AccountRef']['value'])])
                        order_id = self.env['account.move'].search([('backend_id', '=', backend_id),('quickbook_id', '=', rec['Id'])])

                        tax_id = []
                        if lines['AccountBasedExpenseLineDetail']['TaxCodeRef']['value'] == 'TAX':
                            if 'TxnTaxDetail' in rec and 'TxnTaxCodeRef' in rec.get('TxnTaxDetail'):
                                tax_id = [self.env['account.tax'].search([('amount_type', '=', 'group'),('quickbook_id', '=', rec['TxnTaxDetail']['TxnTaxCodeRef']['value'])]).id]
                        
                        order = self.env['account.move.line'].search([('move_id', '=', order_id.id),('quickbook_id', '=', lines['Id']),('name', '=', lines.get('Description'))])
                        
                        result = {'product_id':False,
                            'price_unit': lines['Amount'],
                            'quantity': 1,
                            'account_id': product_account_id.id or None,
                            'product_uom_id': 1,
                            'price_subtotal': lines['Amount'],
                            'name': lines.get('Description') or product_account_id.name,
                            'quickbook_id': lines['Id'],
                            }
                        if not order:
                            product_ids.append([0,0,result]) or False
                        else:
                            product_ids.append([1,order.id,result])

            tax_lines = []
            if 'TxnTaxDetail' in record['Bill']:
                rec_tx = record['Bill'].get('TxnTaxDetail')
                if 'TaxLine' in rec_tx:
                    for line in rec_tx.get('TaxLine'):
                        line_tax = line['TaxLineDetail'].get('TaxRateRef')
                        tax_id = self.env['account.tax'].search([('amount_type', '!=', 'group'),('rate_quickbook_id', '=', line_tax.get('value'))])
                        order_id = self.env['account.move'].search([('backend_id', '=', backend_id),('quickbook_id', '=', record['Bill']['Id'])])                        
                        result = {
                                'name':tax_id.name,
                                'tax_id':tax_id.id or None,
                                'amount':line['Amount'],
                                'manual': False,
                                'company_id':tax_id.company_id.id or None,
                                'currency_id':tax_id.company_id.currency_id.id or None,
                                'base':line['TaxLineDetail'].get('NetAmountTaxable'),
                                }
            if rec['Id']:
                quickbook_id = rec['Id']

            if 'CurrencyRef' in rec.keys():
                currency = self.env['res.currency'].search([('name', '=', rec['CurrencyRef'].get('value'))]).id

        invoice_id = self.env['account.move'].search(
                        [('quickbook_id', '=', quickbook_id),
                          ('backend_id', '=', backend_id)])

        if product_ids:    
            vals= {
            'partner_id': partner_id, 
            'type': inv_type, 
            'doc_number': doc_number or rec.get('DocNumber'),
            'invoice_date_due': date_due or rec['DueDate'],
            'invoice_date': date_invoice or rec['TxnDate'],
            'invoice_line_ids': product_ids,
            'invoice_payment_term_id': payment_term,
            'partner_shipping_id': partner_id,
            'quickbook_id': quickbook_id,
            'backend_id': backend_id,
            'name':'/',
            'currency_id': currency,
            }
            if not invoice_id:
                try:
                    invoice = super(account_invoice, self).create(vals)
                    invoice.action_post()
                    return invoice
                except:
                    raise Warning(_("Issue while importing Invoice " + vals.get('doc_number') + ". Please check if there are any missing values in Quickbooks. If no, then please make sure other dependent fields have been imported first."))
            else:
                invoice = invoice_id.write(vals)
                return invoice

    def invoice_import_batch(self, model_name, backend_id, filters=None):
        """ Import Invoice Details. """
        arguments = 'invoice'
        count = 1
        record_ids = ['start']
        filters['url'] = 'invoice'
        filters['count'] = count
        record_ids = self.get_ids(arguments, backend_id, filters, record_id=False)
            
        if record_ids:
            if 'Invoice' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['Invoice']
                for record_id in record_ids:
                    self.env['account.move'].importer(arguments=arguments, backend_id=backend_id, filters=filters, record_id=int(record_id['Id']))
            else:
                record_ids = record_ids['QueryResponse']

    def bill_import_batch(self, model_name, backend_id, filters=None):
        """ Import Invoice Details. """
        arguments = 'bill'
        count = 1
        record_ids = ['start']
        filters['url'] = 'bill'
        filters['count'] = count
        record_ids = self.get_ids(arguments, backend_id, filters, record_id=False)
            
        if record_ids:
            if 'Bill' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['Bill']
                for record_id in record_ids:
                    self.env['account.move'].importer(arguments=arguments, backend_id=backend_id, filters=filters, record_id=int(record_id['Id']))
            else:
                record_ids = record_ids['QueryResponse']

    def importer(self, arguments, backend_id, filters, record_id):
        
        data = self.get_ids(arguments, backend_id, filters, record_id)
        if data:
            self.invoice_import_mapper(backend_id, data)

    def sync_invoice(self):
        for backend in self.backend_id:
            self.export_invoice_data(backend)
            if self.state == 'paid' and self.payment_ids:
                for payment in self.payment_ids:
                    payment.export_payment_data(backend)
        return

    def sync_bill(self):
        for backend in self.backend_id:
            self.export_bill_data(backend)
            if self.state == 'paid' and self.payment_ids:
                 for payment in self.payment_ids:
                     payment.export_billpayment_data(backend)

    def export_invoice_data(self, backend):
        """ export customer details, save username and create or update backend mapper """
        if not self.backend_id:
            return
        mapper = self.env['account.move'].search(
            [('backend_id', '=', backend.id), ('quickbook_id', '=', self.quickbook_id)], limit=1)
        method = 'invoice'
        arguments = [mapper.quickbook_id or None, self]
        export = QboInvoiceExport(backend)
        res = export.export_invoice(method, arguments)

        if mapper.id == self.id and self.quickbook_id:
            if mapper and (res['status'] == 200 or res['status'] == 201):
                mapper.write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Invoice']['Id']})
                response = res['data']
                count = 0
                for lines in response['Invoice']['Line']:
                    if 'Id' in lines:
                        order_lines = arguments[1].invoice_line_ids
                        order_lines[count].write({'quickbook_id': lines['Id']})
                        count += 1
            elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Invoice']['Id']})
                response = res['data']
                count = 0
                for lines in response['Invoice']['Line']:
                    if 'Id' in lines:
                        order_lines = arguments[1].invoice_line_ids
                        order_lines[count].write({'quickbook_id': lines['Id']})
                        count += 1
        elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Invoice']['Id']})
                response = res['data']
                count = 0
                for lines in response['Invoice']['Line']:
                    if 'Id' in lines:
                        order_lines = arguments[1].invoice_line_ids
                        order_lines[count].write({'quickbook_id': lines['Id']})
                        count += 1

        if res['status'] == 500 or res['status'] == 400:
            for errors in res['errors']['Fault']['Error']:
                msg = errors['Message']
                code = errors['code']
                name = res['name']
                details = 'Message: ' + msg + '\n' + 'Code: ' + code + '\n' + 'Name: '+ str(name.name) + '\n' + 'Detail: ' + errors['Detail']
                if errors['code']:
                    raise Warning(details)

    def export_bill_data(self, backend):
        if not self.backend_id:
            return

        mapper = self.env['account.move'].search(
            [('backend_id', '=', backend.id), ('quickbook_id', '=', self.quickbook_id)], limit=1)
        method = 'bill'
        arguments = [mapper.quickbook_id or None, self]
        export = QboInvoiceExport(backend)
        res = export.export_bill(method, arguments)

        if mapper.id == self.id and self.quickbook_id:
            if mapper and (res['status'] == 200 or res['status'] == 201):
                mapper.write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Bill']['Id']})
                response = res['data']
                count = 0
                for lines in response['Bill']['Line']:
                    if 'Id' in lines:
                        order_lines = arguments[1].invoice_line_ids
                        order_lines[count].write({'quickbook_id': lines['Id']})
                        count += 1
            elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Bill']['Id']})
                response = res['data']
                count = 0
                for lines in response['Bill']['Line']:
                    if 'Id' in lines:
                        order_lines = arguments[1].invoice_line_ids
                        order_lines[count].write({'quickbook_id': lines['Id']})
                        count += 1
        elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Bill']['Id']})
                response = res['data']
                count = 0
                for lines in response['Bill']['Line']:
                    if 'Id' in lines:
                        order_lines = arguments[1].invoice_line_ids
                        order_lines[count].write({'quickbook_id': lines['Id']})
                        count += 1

        if res['status'] == 500 or res['status'] == 400:
            for errors in res['errors']['Fault']['Error']:
                msg = errors['Message']
                code = errors['code']
                name = res['name']
                details = 'Message: ' + msg + '\n' + 'Code: ' + code + '\n' + 'Name: '+ str(name.name) + '\n' + 'Detail: ' + errors['Detail']
                if errors['code']:
                    raise Warning(details)

class quickbook_product(models.Model):

    _inherit = 'account.move.line'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='quick Backend', store=True,
                                 readonly=False, required=False,
                                 )

    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)


class quickbook_acount_tax(models.Model):

    _inherit = 'account.tax'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='quick Backend', store=True,
                                 readonly=False, required=False,
                                 )

    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)


class quickbook_product_product(models.Model):

    _inherit = 'product.product'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='quick Backend', store=True,
                                 readonly=False, required=False,
                                 )

    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)