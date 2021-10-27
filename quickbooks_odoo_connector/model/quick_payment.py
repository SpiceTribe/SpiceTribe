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
from odoo import models, fields, api
from odoo.exceptions import Warning
from requests_oauthlib import OAuth2Session
from ..unit.quick_payment_exporter import QboPaymentExport

_logger = logging.getLogger(__name__)

class quickbook_acount_payment(models.Model):
    _inherit = 'account.payment'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='Quick Backend', store=True,
                                 readonly=False, required=False,
                                 )

    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)
    sync_date = fields.Datetime(string='Last synchronization date')

    @api.model
    def create(self, vals):
        return super(quickbook_acount_payment, self).create(vals)

    def get_ids(self, arguments, backend_id, filters, record_id):

        backend = self.backend_id.browse(backend_id)
        headeroauth = OAuth2Session(backend.client_key)
        headers = {'Authorization': 'Bearer %s' % backend.access_token,
                   'content-type': 'application/json', 'accept': 'application/json'}
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
                data = headeroauth.get(
                    backend.location + backend.company_id + '/' + arguments + '/' + str(record_id) + '?minorversion=4',
                    headers=headers)

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

    def payment_import_mapper(self, backend_id, data):
        record = data
        _logger.info("API DATA :%s", data)
        ID = []
        if 'Payment' in record:
            rec = record['Payment']
            if 'CustomerRef' in rec:
                partner_id = self.env['res.partner'].search(
                    [('quickbook_id', '=', rec['CustomerRef']['value'])])
                if partner_id and partner_id.customer_rank > 0:
                    partner_type = 'customer'
                else:
                    partner_type = 'supplier'
                partner_ids = partner_id.id or False
            else:
                partner_ids = False
                partner_type = None

            if 'Line' in rec:
                for lines in rec['Line']:
                    for trnx in lines['LinkedTxn']:
                        if trnx['TxnType'] == 'Invoice':
                            inv_id = self.env['account.move'].search(
                                [('quickbook_id', '=', trnx['TxnId'])])
                            communication = inv_id.ref or ''
                            amount = lines['Amount'] or None
                            ID = []
                            if inv_id:
                                ID = inv_id.id
                                state = inv_id.state

            if 'Payment' in record:
                journal_id = self.env['account.journal'].search([('type', 'in', ('bank','cash'))], limit=1)
                payment_type = 'inbound'
                payment_method_id = 1

            if 'Line' in rec:
                diffrence = 0.0
                for lines in rec['Line']:
                    for trnx in lines['LinkedTxn']:
                        if trnx['TxnType'] == 'Invoice' or trnx['TxnType'] == 'Bill':
                            inv_id = self.env['account.move'].search(
                                [('quickbook_id', '=', trnx['TxnId'])])
                            amount = lines['Amount'] or None
                            if inv_id.type in ['in_invoice', 'out_refund']:
                                diffrence = amount - inv_id.amount_total
                            else:
                                diffrence = inv_id.amount_total - amount
                if diffrence > 0.0:
                    payment_difference_handling = 'open'
                    writeoff_account_id = None
                else:
                    payment_difference_handling = 'reconcile'
                    writeoff_account_id = partner_id.property_account_receivable_id.id

            if 'TxnDate' in rec:
                payment_date = rec['TxnDate']
            else:
                payment_date = None

            if rec['Id']:
                quickbook_id = rec['Id']

            if rec['TotalAmt']:
                total_amt = rec['TotalAmt']
            else:
                total_amt = 0

            if 'CurrencyRef' in rec.keys():
                currency = self.env['res.currency'].search([('name', '=', rec['CurrencyRef'].get('value'))]).id

        elif 'BillPayment' in record:
            rec = record['BillPayment']
            if 'VendorRef' in rec:
                partner_id = self.env['res.partner'].search(
                    [('quickbook_id', '=', rec['VendorRef']['value'])])
                if partner_id and partner_id.customer_rank > 0:
                    partner_type = 'customer'
                else:
                    partner_type = 'supplier'
                partner_ids = partner_id.id or False

            else:
                partner_ids = False
                partner_type = None

            if 'Line' in rec:
                for lines in rec['Line']:
                    for trnx in lines['LinkedTxn']:
                        if trnx['TxnType'] == 'Bill':
                            inv_id = self.env['account.move'].search(
                                [('quickbook_id', '=', trnx['TxnId'])])
                            communication = inv_id.ref or ''
                            amount = lines['Amount'] or None
                            ID = []
                            if inv_id:
                                ID = inv_id.id
                                state = inv_id.state

            if rec['PayType'] == 'Check':
                payment_method_id = 2
                payment_type = 'outbound'
                journal_id = self.env['account.journal'].search([('type', 'in', ('bank','cash'))], limit=1)
            else:
                payment_method_id = 1
                payment_type = 'outbound'
                journal_id = self.env['account.journal'].search([('type', 'in', ('bank','cash'))], limit=1)

            if 'Line' in rec:
                diffrence = 0.0
                for lines in rec['Line']:
                    for trnx in lines['LinkedTxn']:
                        if trnx['TxnType'] == 'Invoice' or trnx['TxnType'] == 'Bill':
                            inv_id = self.env['account.move'].search(
                                [('quickbook_id', '=', trnx['TxnId'])])
                            amount = lines['Amount'] or None
                            if inv_id.type in ['in_invoice', 'out_refund']:
                                diffrence = amount - inv_id.amount_total
                            else:
                                diffrence = inv_id.amount_total - amount
                if diffrence > 0.0:
                    payment_difference_handling = 'open'
                    writeoff_account_id = None
                else:
                    payment_difference_handling = 'reconcile'
                    writeoff_account_id = partner_id.property_account_receivable_id.id
            if 'TxnDate' in rec:
                payment_date = rec['TxnDate']
            else:
                payment_date = None

            if rec['Id']:
                quickbook_id = rec['Id']

            if rec['TotalAmt']:
                total_amt = rec['TotalAmt']
            else:
                total_amt = 0

            if 'CurrencyRef' in rec.keys():
                currency = self.env['res.currency'].search([('name', '=', rec['CurrencyRef'].get('value'))]).id

        payment_id = self.env['account.payment'].search(
            [('quickbook_id', '=', quickbook_id),
             ('backend_id', '=', backend_id)])
        if ID and state == 'posted':
            vals = {
                'partner_id': partner_ids,
                'partner_type': partner_type,
                'communication': communication,
                'invoice_ids': [(4, ID, None)],
                'payment_date': payment_date or rec['TxnDate'],
                'amount': total_amt,
                'journal_id': journal_id.id,
                'payment_type': payment_type,
                'payment_method_id': payment_method_id,
                'payment_difference': diffrence,
                'payment_difference_handling': payment_difference_handling,
                'writeoff_account_id': writeoff_account_id,
                'backend_id': backend_id,
                'quickbook_id': quickbook_id,
                'currency_id': currency,
            }

            if not payment_id:
                payment = super(quickbook_acount_payment, self).create(vals)
                payment.post()
                return payment
            else:
                payment = payment_id.write(vals)
                return payment

    def payment_import_batch(self, model_name, backend_id, filters=None):
        """ Import Payment Details. """
        arguments = 'payment'
        count = 1
        record_ids = ['start']
        filters['url'] = 'payment'
        filters['count'] = count
        record_ids = self.get_ids(arguments, backend_id, filters, record_id=False)

        if record_ids:
            if 'Payment' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['Payment']
                for record_id in record_ids:
                    self.env['account.payment'].importer(arguments=arguments, backend_id=backend_id,filters=filters, record_id=int(record_id['Id']))
            else:
                record_ids = record_ids['QueryResponse']

    def BillPayment_import_batch(self, model_name, backend_id, filters=None):
        """ Import BillPayment Details. """
        arguments = 'billpayment'
        count = 1
        record_ids = ['start']
        filters['url'] = 'billpayment'
        filters['count'] = count
        record_ids = self.get_ids(arguments, backend_id, filters, record_id=False)

        if record_ids:
            if 'BillPayment' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['BillPayment']
                for record_id in record_ids:
                    self.importer(arguments=arguments, backend_id=backend_id,
                                  filters=filters, record_id=int(record_id['Id']))
            else:
                record_ids = record_ids['QueryResponse']

    def importer(self, arguments, backend_id, filters, record_id):
        data = self.get_ids(arguments, backend_id, filters, record_id)
        if data:
            self.payment_import_mapper(backend_id, data)

    def sync_payment(self):
        for backend in self.backend_id:
            if self.partner_type == 'customer':
                self.export_payment_data(backend)
            elif self.partner_type == 'supplier':
                self.export_billpayment_data(backend)
        return

    def export_payment_data(self, backend):
        """ export payments and create or update backend mapper """
        if not self.backend_id:
            return
        mapper = self.env['account.payment'].search(
            [('backend_id', '=', backend.id), ('quickbook_id', '=', self.quickbook_id)], limit=1)
        method = 'payment'
        arguments = [mapper.quickbook_id or None, self]
        export = QboPaymentExport(backend)
        res = export.export_payment(method, arguments)

        if mapper.id == self.id:
            if mapper and (res['status'] == 200 or res['status'] == 201):
                mapper.write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Payment']['Id']})
            elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Payment']['Id']})
        elif (res['status'] == 200 or res['status'] == 201):
            arguments[1].write(
                {'backend_id': backend.id, 'quickbook_id': res['data']['Payment']['Id']})

        if res['status'] == 500 or res['status'] == 400:
            for errors in res['errors']['Fault']['Error']:
                msg = errors['Message']
                code = errors['code']
                name = res['name']
                details = 'Message: ' + msg + '\n' + 'Code: ' + \
                          code + '\n' + 'Name:' + str(name.name) + '\n' +'Detail: ' + errors['Detail']
                if errors['code']:
                    raise Warning(details)

    def export_billpayment_data(self, backend):
        """ export bill payments and create or update backend mapper """
        if not self.backend_id:
            return
        mapper = self.env['account.payment'].search(
            [('backend_id', '=', backend.id), ('quickbook_id', '=', self.quickbook_id)], limit=1)
        method = 'billpayment'
        arguments = [mapper.quickbook_id or None, self]
        export = QboPaymentExport(backend)
        res = export.export_billpayment(method, arguments)

        if mapper.id == self.id and self.quickbook_id:
            if mapper and (res['status'] == 200 or res['status'] == 201):
                mapper.write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['BillPayment']['Id']})
            elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['BillPayment']['Id']})
        elif (res['status'] == 200 or res['status'] == 201):
            arguments[1].write(
                {'backend_id': backend.id, 'quickbook_id': res['data']['BillPayment']['Id']})

        if res['status'] == 500 or res['status'] == 400:
            for errors in res['errors']['Fault']['Error']:
                msg = errors['Message']
                code = errors['code']
                name = res['name']
                details = 'Message: ' + msg + '\n' + 'Code: ' + \
                          code + '\n' + 'Name: ' + str(name.name) + '\n' + 'Detail: ' + errors['Detail']
                if errors['code']:
                    raise Warning(details)

    @api.model
    def default_get(self, fields):
        res = super(quickbook_acount_payment, self).default_get(fields)
        ids = self.env['qb.backend'].search([]).id
        res['backend_id'] = ids
        return res