# -*- coding: utf-8 -*-
#
#
#    Techspawn Solutions Pvt. Ltd.
#    Copyright (C) 2016-TODAY Techspawn(<http://www.Techspawn.com>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the Methods of the GNU Affero General Public License as
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
from datetime import datetime, timedelta
from odoo.exceptions import Warning, UserError
from .backend_adapter import QuickExportAdapter
from odoo import _

_logger = logging.getLogger(__name__)

class QboAccountExport(QuickExportAdapter):
    """ Models for QBO Account export """

    def get_api_method(self, method, args):
        """ get api for Account"""
        api_method = None
        if method == 'account':
            if not args[0]:
                api_method = self.quick.location + \
                             self.quick.company_id + '/account?minorversion=4'
            else:
                api_method = self.quick.location + self.quick.company_id + '/account?operation=update&minorversion=4'
        return api_method

    def export_account(self, method, arguments):
        """ Export Account data"""
        _logger.debug("Start calling QBO api %s", method)
        if arguments[1].user_type_id.name == 'Bank and Cash':
            account_type = 'Bank'
            account_sub_type = 'CashOnHand'
        elif arguments[1].user_type_id.name == 'Fixed Assets':
            account_type = 'Fixed Asset'
            account_sub_type = 'FurnitureAndFixtures'
        elif arguments[1].user_type_id.name == 'Current Assets':
            account_type = 'Other Current Asset'
            account_sub_type = 'Inventory'
        elif arguments[1].user_type_id.name == 'Income':
            account_type = 'Income'
            account_sub_type = 'SalesOfProductIncome'
        elif arguments[1].user_type_id.name == 'Receivable':
            account_type = 'Accounts Receivable'
            account_sub_type = 'AccountsReceivable'
        elif arguments[1].user_type_id.name == 'Current Liabilities':
            account_type = 'Other Current Liability'
            account_sub_type = 'OtherCurrentLiabilities'
        elif arguments[1].user_type_id.name == 'Payable':
            account_type = 'Accounts Payable'
            account_sub_type = 'AccountsPayable'
        elif arguments[1].user_type_id.name == 'Expenses':
            account_type = 'Expense'
            account_sub_type = 'Travel'
        elif arguments[1].user_type_id.name == 'Current Year Earnings':
            account_type = 'Other Current Liability'
            account_sub_type = 'OtherCurrentLiabilities'
        elif arguments[1].user_type_id.name == 'Prepayments':
            account_type = ' Other Expense'
            account_sub_type = 'Depreciation'
        elif arguments[1].user_type_id.name == 'Non-current Assets':
            account_type = 'Other Expense'
            account_sub_type = 'Depreciation'
        elif arguments[1].user_type_id.name == 'Non-current Liabilities':
            account_type = 'Other Expense'
            account_sub_type = 'Depreciation'
        elif arguments[1].user_type_id.name == 'Depreciation':
            account_type = 'Other Expense'
            account_sub_type = 'Depreciation'
        elif arguments[1].user_type_id.name == 'Cost of Revenue':
            account_type = 'Cost of Goods Sold'
            account_sub_type = 'SuppliesMaterialsCogs'
        else:
            account_type = arguments[1].user_type_id.name
            account_sub_type = None

        result_dict = {
            "Name": arguments[1].name,
            "AccountType": account_type,
            "AccountSubType": account_sub_type or None
        }
        if '?operation=update&minorversion=4' in self.get_api_method(method, arguments):
            result = self.importer_updater(method, arguments)
            result_dict.update({
                "sparse": result['Account']['sparse'],
                "Id": result['Account']['Id'],
                "SyncToken": result['Account']['SyncToken'], })
        res = self.export(method, result_dict, arguments)
        if res:
            res_dict = res.json()
            errors_dict = None
        else:
            res_dict = None
            errors_dict = res.json()
        return {'status': res.status_code, 'data': res_dict or {}, 'errors': errors_dict or {}, 'name': arguments[1]}