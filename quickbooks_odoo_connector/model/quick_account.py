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

from odoo import models, fields, api, _
from odoo.exceptions import Warning
from datetime import datetime
from requests_oauthlib import OAuth2Session
import random
from ..unit.quick_account_exporter import QboAccountExport

_logger = logging.getLogger(__name__)

class quickbook_acount(models.Model):
    _inherit = 'account.account'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='Quick Backend', store=True,
                                 readonly=False, required=False,
                                 )
    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)
    sync_date = fields.Datetime(string='Last synchronization date')

    def get_ids(self, arguments, backend_id, filters, record_id):
        backend = self.backend_id.browse(backend_id)
        headeroauth = OAuth2Session(backend.client_key)
        headers = {'Authorization': 'Bearer %s' % backend.access_token,
                   'content-type': 'application/json', 'accept': 'application/json'}
        method = '/query?query=select%20ID%20from%20'
        if not record_id:
            data = headeroauth.get(backend.location + backend.company_id +
                                   method + arguments + '%20STARTPOSITION%20' + str(filters['count']) + '%20MAXRESULTS%20' + str(300) + '&minorversion=54', headers=headers)
        else:
            data = headeroauth.get(backend.location + backend.company_id +
                                   '/' + arguments + '/' + str(record_id) + '?minorversion=54', headers=headers)
            if data.status_code == 429:
                self.env.cr.commit()
                time.sleep(60)
                data = headeroauth.get(
                    backend.location + backend.company_id + '/' + arguments + '/' + str(record_id) + '?minorversion=54',
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

    def account_import_mapper(self, backend_id, data):
        record = data
        _logger.info("API DATA :%s", data)
        if 'Account' in record:
            rec = record['Account']
            reconcile = False
            if 'Name' in rec:
                name = rec['Name']
                code = self.env['ir.sequence'].next_by_code('account.account')
            else:
                name = False
                code = False
            if 'Active' in rec:
                active = rec['Active']
            if 'CurrentBalance' in rec:
                balance = rec['CurrentBalance']
            if 'AccountType' in rec:
                user_type = self.env['account.account.type'].search(
                    [('name', '=', rec['AccountType'])])
                if not user_type:
                    user_type = self.env['account.account.type'].create(
                        {   'name':  rec.get('AccountType'),
                            'internal_group': rec.get('Classification').lower()
                         })
                user_type = user_type.id or False
                if rec['AccountType'] == 'Accounts Receivable' or rec['AccountType'] == 'Accounts Payable':
                    reconcile = True
            else:
                user_type = False
            if rec['Id']:
                quickbook_id = rec['Id']
                
        account_id = self.env['account.account'].search(
            [('quickbook_id', '=', quickbook_id), ('backend_id', '=', backend_id)])
        vals = {
            'name': name,
            'code': code,
            'user_type_id': user_type,
            'backend_id': backend_id,
            'quickbook_id': quickbook_id,
            'reconcile': reconcile
        }
        if not account_id:
            try:
                return super(quickbook_acount, self).create(vals)
            except:
                raise Warning(_("Issue while importing Account " + vals.get('name') + ". Please check if there are any missing values in Quickbooks."))

        else:
            for ac_id in account_id:
                account = ac_id.write(vals)
                return account

    def account_import_batch_new(self, model_name, backend_id, filters=None):
        """ Import Account Details. """
        arguments = 'account'
        count = 1
        record_ids = ['start']
        filters['url'] = 'account'
        filters['count'] = count
        record_ids = self.get_ids(arguments, backend_id, filters, record_id=False)

        if record_ids:
            if 'Account' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['Account']
                for record_id in record_ids:
                    self.env['account.account'].importer(arguments=arguments, backend_id=backend_id,
                                                                         filters=filters,
                                                                         record_id=int(record_id['Id']))
            else:
                record_ids = record_ids['QueryResponse']

    def importer(self, arguments, backend_id, filters, record_id):
        data = self.get_ids(arguments, backend_id, filters, record_id)
        if data:
            self.account_import_mapper(backend_id, data)

    def sync_account(self):
        for backend in self.backend_id:
            self.export_account_data(backend)
        return

    def sync_account_multiple(self):
        for rec in self:
            for backend in rec.backend_id:
                rec.export_account_data(backend)
        return

    def export_account_data(self, backend):
        """ export account and create or update backend """
        if not self.backend_id:
            return
        mapper = self.env['account.account'].search(
            [('backend_id', '=', backend.id), ('quickbook_id', '=', self.quickbook_id)], limit=1)
        method = 'account'
        arguments = [mapper.quickbook_id or None, self]
        export = QboAccountExport(backend)
        res = export.export_account(method, arguments)

        if mapper.id == self.id and self.quickbook_id:
            if mapper and (res['status'] == 200 or res['status'] == 201):
                mapper.write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Account']['Id']})
            elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Account']['Id']})
        elif (res['status'] == 200 or res['status'] == 201):
            arguments[1].write(
                {'backend_id': backend.id, 'quickbook_id': res['data']['Account']['Id']})

        if res['status'] == 500 or res['status'] == 400:
            for errors in res['errors']['Fault']['Error']:
                msg = errors['Message']
                code = errors['code']
                name = res['name']
                details = 'Message: ' + msg + '\n' + 'Code: ' + \
                          code + '\n' + 'Name: ' + str(name.name) + '\n' + 'Detail: ' + errors['Detail']
                if errors['code'] == '2090':
                    raise UserError(
                        _("Please Check Whether Income Account Field and Expense Account Field Empty Or Not Synced "))
                else:
                    raise Warning(details)

    @api.model
    def default_get(self, fields):
        res = super(quickbook_acount, self).default_get(fields)
        ids = self.env['qb.backend'].search([]).id
        res['backend_id'] = ids
        return res