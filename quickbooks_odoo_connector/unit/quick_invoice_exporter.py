# -*- coding: utf-8 -*-
#
#
#    Techspawn Solutions Pvt. Ltd.
#    Copyright (C) 2016-TODAY Techspawn(<http://www.Techspawn.com>).
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
from datetime import datetime, timedelta
from .backend_adapter import QuickExportAdapter
from odoo.exceptions import Warning, UserError
from odoo import _

_logger = logging.getLogger(__name__)


class QboInvoiceExport(QuickExportAdapter):
    """ Models for QBO customer export """

    def get_api_method(self, method, args):
        """ get api for Product/item"""
        api_method = None
        if method == 'invoice':
            if not args[0]:
                api_method = self.quick.location + \
                             self.quick.company_id + '/invoice?minorversion=4'
            else:
                api_method = self.quick.location + self.quick.company_id + '/invoice?operation=update&minorversion=4'
        if method == 'bill':
            if not args[0]:
                api_method = self.quick.location + \
                             self.quick.company_id + '/bill?minorversion=4'
            else:
                api_method =  self.quick.location + self.quick.company_id + '/bill?operation=update&minorversion=4'
        return api_method

    def export_invoice(self, method, arguments):
        """ Export Invoice data"""
        _logger.debug("Start calling QBO api %s", method)

        temp_array = []
        taxcodeqb_id = None
        if arguments[1].invoice_line_ids:
            for order_line in arguments[1].invoice_line_ids:
                product_template_id = arguments[1].env['product.template'].search(
                    [('name', '=', order_line.product_id.name)])
                if order_line.tax_ids:
                    taxcoderef = "TAX"
                    taxcodeqb_id = order_line.tax_ids.quickbook_id
                else:
                    taxcoderef = "NON"

                temp = {
                    "Description": order_line.name or None,
                    "Amount": order_line.price_subtotal,
                    "DetailType": "SalesItemLineDetail",
                    "SalesItemLineDetail": {
                        "ItemRef": {
                            "value": product_template_id.quickbook_id or None,
                        },
                        "UnitPrice": order_line.price_unit,
                        "Qty": order_line.quantity,
                        "TaxCodeRef": {
                            "value": taxcoderef,
                        }
                    },
                    "Id": order_line.quickbook_id or None,
                }
                if not arguments[1].env.company.partner_id.country_id.code is 'US':
                    temp.get("SalesItemLineDetail").get('TaxCodeRef').update({'value': taxcodeqb_id })
                temp_array.append(temp)
        result_dict = {
            "TxnDate": arguments[1].invoice_date,
            "DocNumber": arguments[1].doc_number,
            "Line": temp_array,
            "TxnTaxDetail": {
                "TxnTaxCodeRef": {
                    "value": taxcodeqb_id or None
                },
            },
            "CustomerRef": {
                "value": arguments[1].partner_id.quickbook_id,
            },
            "DueDate": arguments[1].invoice_date_due,
            "BillEmail": {
                "Address": arguments[1].partner_id.email or None
            },
            "SalesTermRef": {
                "value": arguments[1].invoice_payment_term_id.quickbook_id or None,
            },
        }

        if arguments[1].currency_id:
            result_dict.update({
                "CurrencyRef": {
                   "value": str(arguments[1].currency_id.name)
                  }
                })

        if '?operation=update&minorversion=4' in self.get_api_method(method, arguments):
            result = self.importer_updater(method, arguments)
            result_dict.update({
                "sparse": result['Invoice']['sparse'],
                "Id": result['Invoice']['Id'],
                "SyncToken": result['Invoice']['SyncToken'], })
        res = self.export(method, result_dict, arguments)
        if res:
            res_dict = res.json()
            errors_dict = None
        else:
            res_dict = None
            errors_dict = res.json()
        return {'status': res.status_code, 'data': res_dict or {}, 'errors': errors_dict or {}, 'name': arguments[1]}

    def export_bill(self, method, arguments):
        """" Export Bill Data """

        _logger.debug("Start calling QBO api %s", method)

        temp_array = []
        taxcodeqb_id = None
        if arguments[1].invoice_line_ids:
            for order_line in arguments[1].invoice_line_ids:
                product_template_id = arguments[1].env['product.template'].search(
                    [('name', '=', order_line.product_id.name)])
                if order_line.tax_ids:
                    taxcoderef = "TAX"
                    taxcodeqb_id = order_line.tax_ids.quickbook_id
                else:
                    taxcoderef = "NON"

                temp = {

                    "Description" : order_line.name or None,
                    "Amount" : order_line.price_subtotal,
                    "DetailType" : "ItemBasedExpenseLineDetail",
                    "ItemBasedExpenseLineDetail" : {
                        "ItemRef" : {
                            "value" : product_template_id.quickbook_id or None
                        },
                    "UnitPrice" : order_line.price_unit,
                    "Qty" : order_line.quantity,
                    "TaxCodeRef" : { 
                        "value" : taxcoderef
                        }
                    },
                    "Id" : order_line.quickbook_id or None
                }
                if not arguments[1].env.company.partner_id.country_id.code is 'US':
                    temp.get("SalesItemLineDetail").get('TaxCodeRef').update({'value': taxcodeqb_id })
                temp_array.append(temp)
        result_dict = {
                    "TxnDate": arguments[1].invoice_date,
                    "DocNumber": arguments[1].doc_number,
                    "Line": temp_array,
                    "TxnTaxDetail": {
                        "TxnTaxCodeRef": {
                            "value": taxcodeqb_id or None
                         },
                    },
                    "VendorRef": {
                        "value": arguments[1].partner_id.quickbook_id,
                        },
                    "DueDate": arguments[1].invoice_date_due,
                    "BillEmail": {
                    "Address": arguments[1].partner_id.email or None
                       },
                    "SalesTermRef": {
                    "value": arguments[1].invoice_payment_term_id.quickbook_id or None,
                    },
        }

        if arguments[1].currency_id:
            result_dict.update({
                "CurrencyRef": {
                   "value": str(arguments[1].currency_id.name)
                  }
                })

        if '?operation=update&minorversion=4' in self.get_api_method(method, arguments):
            result = self.importer_updater(method, arguments)
            result_dict.update({
                "sparse": result['Bill']['sparse'], 
                "Id": result['Bill']['Id'],
                "SyncToken": result['Bill']['SyncToken'], })

                    
        res = self.export(method, result_dict, arguments)
        if res:
            res_dict = res.json()
            errors_dict = None
        else:
            res_dict = None
            errors_dict = res.json()
        return {'status': res.status_code, 'data': res_dict or {}, 'errors': errors_dict or {}, 'name': arguments[1]}