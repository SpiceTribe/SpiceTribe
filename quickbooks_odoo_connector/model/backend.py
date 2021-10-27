import webbrowser

from base64 import b64encode
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from requests_oauthlib import OAuth1Session, OAuth2Session
from ..unit.quick_payment_exporter import QboPaymentExport

class bk_backend(models.Model):
    _name = 'qb.backend'
    _description = 'Quickbook Backend Configuration'

    name = fields.Char(string='name')
    location = fields.Char("Url", required=True, default="Enter url")
    client_key = fields.Char("Consumer key", required=True, default='Enter key')
    client_secret = fields.Char("Consumer Secret", required=True, default='Enter secret')
    type = fields.Selection([('oauth1', 'OAuth1'),
                             ('oauth2', 'OAuth2')],
                            default='oauth2',
                            string='Oauth Type')
    version = fields.Selection([('v2', 'V2'),
                                ('v3', 'V3')], 'Version')

    # oauth1 fields
    request_token_url = fields.Char(
        "Request Token URl", default='https://oauth.intuit.com/oauth/v1/get_request_token')
    access_token_url = fields.Char(
        "Access Token URl", default='https://oauth.intuit.com/oauth/v1/get_access_token')
    authorization_base_url = fields.Char(
        "Authorization Base URl", default='https://appcenter.intuit.com/connect/begin')
    company_id = fields.Char("Company Id")
    resource_owner_key = fields.Char(string="Token Key")
    resource_owner_secret = fields.Char(string="Token Secret")
    signature_method = fields.Char(string="Signature Method")
    verify_ssl = fields.Boolean("Verify SSL")
    default_lang_id = fields.Many2one(
        comodel_name='res.lang',
        string='Default Language',
        help="If a default language is selected, the records "
             "will be imported in the translation of this language.\n"
             "Note that a similar configuration exists "
             "for each storeview.",
    )
    asset_account_ref = fields.Many2one(
        comodel_name='account.account',
        string="Asset Account",
    )
    new_url = fields.Char("Authorized New Url")
    go_to = fields.Char("Go to this link")

    # oauth2 fields
    redirect_uri = fields.Char("Redirect URI", required=True, default='https://www.getpostman.com/oauth2/callback')
    oauth2_authorization_base_url = fields.Char("Authorization Base URL", required=True,
                                                default='https://appcenter.intuit.com/connect/oauth2')
    token_url = fields.Char("Token URL", required=True,
                            default='https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer')
    scope = fields.Selection([
        ('com.intuit.quickbooks.accounting', 'Accounting'),
        ('com.intuit.quickbooks.payment', 'Payment'),
        ('all', 'All')],
        string='Scope', default='com.intuit.quickbooks.accounting')
    token_type = fields.Char(string='Token Type',
                             help='Identifies the type of token returned. At this time, this field will always have the value Bearer')
    x_refresh_token_expires_in = fields.Char(string='X Refresh Token Expires In ',
                                             help='The remaining lifetime, in seconds, for the connection, after which time the user must re-grant access, See refresh_token policy for details.')
    refresh_token = fields.Char(string='Refresh Token', help='A token used when refreshing the access token.')
    access_token = fields.Char(string='Access Token', help='The token that must be used to access the QuickBooks API.')
    expires_in = fields.Char(string='Expires In',
                             help='The remaining lifetime of the access token in seconds. The value always returned is 3600 seconds (one hour). Use the refresh token to get a fresh one')
    expires_at = fields.Char(string='Expires At',
                             help='The remaining lifetime of the access token in seconds. The value always returned is 3600 seconds (one hour). Use the refresh token to get a fresh one. See Refreshing the access token for further information.')
    token = fields.Char(string='Token', help='The token that must be used to access the QuickBooks API.')
    o2_auth_url = fields.Char("Authorized Url")
    o2_go_to = fields.Char("Go to link")

    # Two step oauth2 authorization 
    def qb_authorization_o2_step1(self):
        if self.scope == 'all':
            scope = ['com.intuit.quickbooks.accounting',
                     'com.intuit.quickbooks.payment',
                     'openid',
                     'profile',
                     'email',
                     'phone',
                     'address']
        elif self.scope == 'com.intuit.quickbooks.accounting':
            scope = self.scope
        elif self.scope == 'com.intuit.quickbooks.payment':
            scope = self.scope
        qbo = OAuth2Session(self.client_key, scope=scope, redirect_uri=self.redirect_uri)
        authorization_url, state = qbo.authorization_url(self.oauth2_authorization_base_url)
        print('Please go here and authorize,', authorization_url)
        self.write({'o2_go_to': authorization_url,
                    'o2_auth_url': self.o2_auth_url, })

    def qb_authorization_o2_step2(self):
        if self.scope == 'all':
            scope = ['com.intuit.quickbooks.accounting',
                     'com.intuit.quickbooks.payment',
                     'openid',
                     'profile',
                     'email',
                     'phone',
                     'address']
        elif self.scope == 'com.intuit.quickbooks.accounting':
            scope = self.scope
        elif self.scope == 'com.intuit.quickbooks.payment':
            scope = self.scope
        qbo = OAuth2Session(self.client_key, scope=scope, redirect_uri=self.redirect_uri)
        redirect_response = self.o2_auth_url
        fetch_toke = qbo.fetch_token(self.token_url, client_secret=self.client_secret,
                                     authorization_response=redirect_response)
        print(fetch_toke)
        self.write({'token_type': fetch_toke.get('token_type'),
                    'x_refresh_token_expires_in': fetch_toke.get('x_refresh_token_expires_in'),
                    'refresh_token': fetch_toke.get('refresh_token'),
                    'access_token': fetch_toke.get('access_token'),
                    'expires_in': fetch_toke.get('expires_in'),
                    'expires_at': fetch_toke.get('expires_at')})
        self.write({'token': fetch_toke})
        con_url = self.location + self.company_id + '/customer/1'
        r = qbo.get(con_url)
        print(r.content)

    def qb_auth_o2_auto_step2(self, context):
        obj = self.env['qb.backend'].search([('id', '=', context['id'])])
        if context['scope'] == 'all':
            scope = ['com.intuit.quickbooks.accounting',
                     'com.intuit.quickbooks.payment',
                     'openid', 'profile', 'email', 'phone', 'address']
        elif context['scope'] == 'com.intuit.quickbooks.accounting':
            scope = context['scope']
        elif context['scope'] == 'com.intuit.quickbooks.payment':
            scope = context['scope']
        qbo = OAuth2Session(context['client_key'], scope=scope, redirect_uri=context['redirect_uri'])
        redirect_response = context['o2_auth_url']
        fetch_toke = qbo.fetch_token(context['token_url'], client_secret=context['client_secret'],
                                     authorization_response=redirect_response)
        print(fetch_toke)
        obj.write({'token_type': fetch_toke.get('token_type'),
                   'x_refresh_token_expires_in': fetch_toke.get('x_refresh_token_expires_in'),
                   'refresh_token': fetch_toke.get('refresh_token'),
                   'access_token': fetch_toke.get('access_token'),
                   'expires_in': fetch_toke.get('expires_in'),
                   'expires_at': fetch_toke.get('expires_at')})
        obj.write({'token': fetch_toke})
        con_url = context['location'] + context['company_id'] + '/customer/1'
        r = qbo.get(con_url)
        print(r.content)

    def test_connection(self):
        """ Test backend connection """
        location = self.location
        cons_key = self.client_key
        sec_key = self.client_secret
        version = self.version
        verify_ssl = self.verify_ssl
        headerauth = OAuth2Session(cons_key)
        headers = {'Authorization': 'Bearer %s' % self.access_token, 'content-type': 'application/json',
                   'accept': 'application/json'}
        con_url = self.location + self.company_id + '/customer/1'
        re = headerauth.get(con_url, headers=headers)

        if re.status_code == 404:
            raise Warning(_("Enter Valid url"))

        val = re.json()

        msg = ''
        if 'errors' in re.json():
            msg = val['errors'][0]['message'] + '\n' + val['errors'][0]['code']
            raise Warning(_(msg))
        elif re.status_code == 200:
            raise UserError(_("Connection Test Succeeded! Everything seems properly set up!"))
        elif re.status_code == 400 and val['Fault']['Error'][0]['code'] == '610':
            raise UserError(_("Connection Establised! Something you're trying to use has been made inactive"))
        else:
            raise UserError(_(
                "Connection Lost! Please check the values entered and extra space after the values given by mistake or Refresh the Connection"))

    def refresh_connection(self):
        """ Refresh backend connection """

        headeroauth = OAuth2Session(self.client_key)

        client_cred = (self.client_key + ":" + self.client_secret).encode('utf-8')
        b = bytes(client_cred)
        auth = "Basic " + b64encode(b).decode('utf-8')

        api_method = 'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer'

        headers = {
            'authorization': auth,
            'accept': 'application/json',
            'content-type': 'application/x-www-form-urlencoded',
        }
        body = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token
        }
        fetch_toke = headeroauth.post(api_method, data=body, headers=headers)

        if fetch_toke.status_code == 200:
            keys = fetch_toke.json()
            self.write({'refresh_token': keys['refresh_token'],
                        'access_token': keys['access_token'],
                        'token_type': keys['token_type'],
                        'x_refresh_token_expires_in': keys['x_refresh_token_expires_in'],
                        'expires_in': keys['expires_in'], })
            self.write({'token': fetch_toke})
        print(fetch_toke.content)

    def refresh_connection_action(self):

        """ Refresh backend connection """

        self = self.search([('type', '=', 'oauth2')])
        headeroauth = OAuth2Session(self.client_key)

        client_cred = (self.client_key + ":" + self.client_secret).encode('utf-8')
        b = bytes(client_cred)
        auth = "Basic " + b64encode(b).decode('utf-8')

        api_method = 'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer'
        headers = {
            'authorization': auth,
            'accept': 'application/json',
            'content-type': 'application/x-www-form-urlencoded',
        }
        body = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token
        }
        fetch_toke = headeroauth.post(api_method, data=body, headers=headers)
        if fetch_toke.status_code == 200:
            keys = fetch_toke.json()
            self.write({'refresh_token': keys['refresh_token'],
                        'access_token': keys['access_token'],
                        'token_type': keys['token_type'],
                        'x_refresh_token_expires_in': keys['x_refresh_token_expires_in'],
                        'expires_in': keys['expires_in'], })
            self.write({'token': fetch_toke})
        print(fetch_toke.content)

    def qb_authorization(self):

        oauth = OAuth1Session(self.client_key, self.client_secret,
                              callback_uri='http://localhost:8069/web/auth/')
        request_response = oauth.fetch_request_token(self.request_token_url)
        self.write({'resource_owner_key': request_response.get('oauth_token')})
        self.write(
            {'resource_owner_secret': request_response.get('oauth_token_secret')})
        # 3. Redirect user to your provider implementation for authorization
        # Cut and paste the authorization_url and run it in a browser
        authorization_url = oauth.authorization_url(
            self.authorization_base_url)
        print('Please go here and authorize,', authorization_url)
        webbrowser.open(authorization_url)
        self.write({'go_to': authorization_url})
        # 4. Get the authorization verifier code from the casllback url
        # redirect response is the complete callback_uri after you have
        # authorized access to a company
        # string_vals = request.httprequest.query_string

    def qb_authorization_step2(self):

        oauth = OAuth1Session(self.client_key, self.client_secret,
                              self.resource_owner_key, self.resource_owner_secret)
        redirect_response = self.new_url
        data = oauth.parse_authorization_response(redirect_response)
        self.write({'company_id': data.get('realmId')})
        # 5. Fetch the access token
        # At this point, oauth session object already has the request token and
        # At this point, oauth session object already has the request token and
        # request token secret
        fetch_response = oauth.fetch_access_token(self.access_token_url)
        self.write({'resource_owner_key': fetch_response.get('oauth_token')})
        self.write(
            {'resource_owner_secret': fetch_response.get('oauth_token_secret')})

    def import_account(self):
        import_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        backend_id = self.id
        from_date = None
        self.env['quickbook.accounts'].account_import_batch(
            model_name='quickbook.accounts', backend_id=backend_id,
            filters={'from_date': from_date,
                     'to_date': import_start_time}
        )
        return True

    def import_accounts(self):
        """ Import Accounts from QBO """
        for backend in self:
            backend.import_account()
        return True

    def import_account_new(self):
        import_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        backend_id = self.id
        from_date = None
        self.env['account.account'].account_import_batch_new(
            model_name='account.account', backend_id=backend_id,
            filters={'from_date': from_date,
                     'to_date': import_start_time}
        )
        return True

    def import_accounts_new(self):
        """ Import Accounts from QBO """
        for backend in self:
            backend.import_account_new()
        return True

    def import_taxcode(self):
        import_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        backend_id = self.id
        from_date = None
        self.env['account.tax'].tax_import_batch(
            model_name='account.tax', backend_id=backend_id,
            filters={'from_date': from_date,
                     'to_date': import_start_time}
        )
        return True

    def import_taxes(self):
        """ Import Tax Code From QBO """
        for backend in self:
            backend.import_taxcode()
        return True

    def import_employee(self):
        import_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        backend_id = self.id
        from_date = None
        self.env['quickbook.employees'].employee_import_batch(
            model_name='quickbook.employees', backend_id=backend_id,
            filters={'from_date': from_date,
                     'to_date': import_start_time}
        )
        return True

    def import_employees(self):
        """ Import Employees From QBO """
        for backend in self:
            backend.import_employee()
        return True

    def import_employee_new(self):
        import_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        backend_id = self.id
        from_date = None
        self.env['hr.employee'].employee_import_batch_new(
            model_name='hr.employee', backend_id=backend_id,
            filters={'from_date': from_date,
                     'to_date': import_start_time}
        )
        return True

    def import_employees_new(self):
        """ Import Employees From QBO """
        for backend in self:
            backend.import_employee_new()
        return True

    def import_department(self):
        import_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        backend_id = self.id
        from_date = None
        self.env['hr.department'].department_import_batch(
            model_name='hr.department', backend_id=backend_id,
            filters={'from_date': from_date,
                     'to_date': import_start_time}
        )
        return True

    def import_departments(self):
        """ Import Department From QBO """
        for backend in self:
            backend.import_department()
        return True

    def import_invoice(self):
        import_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        backend_id = self.id
        from_date = None
        self.env['account.move'].invoice_import_batch(
            model_name='account.move', backend_id=backend_id,
            filters={'from_date': from_date,
                     'to_date': import_start_time}
        )
        return True

    def import_invoices(self):
        """ Import Invoices from QBO """
        for backend in self:
            backend.import_invoice()
        return True

    def import_bill(self):
        import_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        backend_id = self.id
        from_date = None
        self.env['account.move'].bill_import_batch(
            model_name='account.move', backend_id=backend_id,
            filters={'from_date': from_date,
                     'to_date': import_start_time}
        )
        return True

    def import_bills(self):
        """ Import categories from all websites """
        for backend in self:
            backend.import_bill()
        return True

    def import_billpayment(self):
        import_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        backend_id = self.id
        from_date = None
        self.env['account.payment'].BillPayment_import_batch(
            model_name='account.payment', backend_id=backend_id,
            filters={'from_date': from_date,
                     'to_date': import_start_time}
        )
        return True

    def import_billpayments(self):
        """ Import Vendor Bill Payment from all websites """
        for backend in self:
            backend.import_billpayment()
        return True

    def import_journal(self):
        import_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        backend_id = self.id
        from_date = None
        self.env['account.journal'].journal_batch_new(
            model_name='account.journal', backend_id=backend_id,
            filters={'from_date': from_date,
                     'to_date': import_start_time}
        )
        return True

    def import_journals(self):
        """ Import journal Payment from all websites """
        for backend in self:
            backend.import_journal()
        return True

    def import_invoicePayment(self):
        import_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        backend_id = self.id
        from_date = None
        self.env['account.payment'].payment_import_batch(
            model_name='account.payment', backend_id=backend_id,
            filters={'from_date': from_date,
                     'to_date': import_start_time}
        )
        return True

    def import_invoicePayments(self):
        """ Import Cutsomer Invoice Payment from all websites """
        for backend in self:
            backend.import_invoicePayment()
        return True

    def import_term(self):
        import_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        backend_id = self.id
        from_date = None
        self.env['account.payment.term'].term_import_batch(
            model_name='account.payment.term', backend_id=backend_id,
            filters={'from_date': from_date,
                     'to_date': import_start_time}
        )
        return True

    def import_terms(self):
        """ Import Terms From QBO """
        for backend in self:
            backend.import_term()
        return True

    def import_payment_method(self):
        import_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        backend_id = self.id
        from_date = None
        self.env['payment.acquirer'].payment_method_import_batch(
            model_name='payment.acquirer', backend_id=backend_id,
            filters={'from_date': from_date,
                     'to_date': import_start_time}
        )
        return True

    def import_payment_methods(self):
        """ Import Payment Method From QBO """
        for backend in self:
            backend.import_payment_method()
        return True

    def import_customer_new(self):
        import_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        backend_id = self.id
        from_date = None
        self.env['res.partner'].customer_import_batch_new(
            model_name='res.partner', backend_id=backend_id,
            filters={'from_date': from_date,
                     'to_date': import_start_time}
        )
        return True

    def import_customers_new(self):
        """ Import categories from all websites """
        for backend in self:
            backend.import_customer_new()
        return True

    def import_customer(self):
        import_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        backend_id = self.id
        from_date = None
        self.env['quickbook.customers'].customer_import_batch(
            model_name='quickbook.customers', backend_id=backend_id,
            filters={'from_date': from_date,
                     'to_date': import_start_time}
        )
        return True

    def import_customers(self):
        """ Import Employees From QBO """
        for backend in self:
            backend.import_customer()
        return True

    def import_vendor_qb(self):
        import_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        backend_id = self.id
        from_date = None
        self.env['quickbook.vendors'].vendor_import_batch(
            model_name='quickbook.vendors', backend_id=backend_id,
            filters={'from_date': from_date,
                     'to_date': import_start_time}
        )
        return True

    def import_vendors_qb(self):
        """ Import categories from all websites """
        for backend in self:
            backend.import_vendor_qb()
        return True

    def import_vendor_new(self):
        import_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        backend_id = self.id
        from_date = None
        self.env['res.partner'].vendor_import_batch_new(
            model_name='res.partner', backend_id=backend_id,
            filters={'from_date': from_date,
                     'to_date': import_start_time}
        )
        return True

    def import_vendors_new(self):
        """ Import categories from all websites """
        for backend in self:
            backend.import_vendor_new()
        return True

    def import_product(self):
        import_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        backend_id = self.id
        from_date = None
        self.env['quickbook.products'].item_import_batch(
            model_name='quickbook.products', backend_id=backend_id,
            filters={'from_date': from_date,
                     'to_date': import_start_time}
        )
        return True

    def import_products(self):
        """ Import product or item from QBO """
        for backend in self:
            backend.import_product()
        return True

    def import_product_new(self):
        import_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        backend_id = self.id
        from_date = None
        self.env['product.template'].item_import_batch_new(
            model_name='product.template', backend_id=backend_id,
            filters={'from_date': from_date,
                     'to_date': import_start_time}
        )
        return True

    def import_products_new(self):
        """ Import product or item from QBO """
        for backend in self:
            backend.import_product_new()
        return True

    def import_sale(self):
        import_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        backend_id = self.id
        from_date = None
        self.env['sale.order'].sale_import_batch(
            model_name='sale.order', backend_id=backend_id,
            filters={'from_date': from_date,
                     'to_date': import_start_time}
        )
        return True

    def import_sales(self):
        """ Import SalesReceipt from all websites """
        for backend in self:
            backend.import_sale()
        return True

    def import_purchase(self):
        import_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        backend_id = self.id
        from_date = None
        self.env['purchase.order'].purchase_import_batch(
            model_name='purchase.order', backend_id=backend_id,
            filters={'from_date': from_date,
                     'to_date': import_start_time}
        )
        return True

    def import_purchases(self):
        """ Import purchase from QBO """
        for backend in self:
            backend.import_purchase()
        return True

    def export_customers(self):
        """ Export all the customers of particular backend """
        all_customers = self.env['res.partner'].search(
            [('backend_id', '=', self.id), ('customer_rank', '>', 0)])
        for customer in all_customers:
            customer.export_customer_data(self)
        return True

    def export_vendors(self):
        """ Export all the customers of particular backend """
        all_vendors = self.env['res.partner'].search(
            [('backend_id', '=', self.id), ('supplier_rank', '>', 0)])
        for vendor in all_vendors:
            vendor.export_vendor_data(self)
        return True

    def export_items(self):
        """ Export all the Product/items of particular backend """
        all_items = self.env['product.template'].search(
            [('backend_id', '=', self.id)])
        for item in all_items:
            item.export_product_data(self)
        return True

    def export_payment_methods(self):
        """ Export all the Payment methods of particular backend """
        all_pay_methods = self.env['payment.acquirer'].search(
            [('backend_id', '=', self.id)])
        for methods in all_pay_methods:
            methods.export_payment_method_data(self)
        return True

    def export_purchases(self):
        """ Export all the Payment methods of particular backend """
        all_purchase = self.env['purchase.order'].search(
            [('backend_id', '=', self.id)])
        for purchase in all_purchase:
            purchase.export_purchase_data(self)
        return True

    def export_invoice(self):
        """ Export all the Invoices of particular backend """
        all_invoice = self.env['account.move'].search(
            [('backend_id', '=', self.id), ('type', '=', 'out_invoice')])
        for invoice in all_invoice:
            invoice.export_invoice_data(self)
        return True

    def export_employees(self):
        """ Export all the Employees of particular backend """
        all_emp = self.env['hr.employee'].search(
            [('backend_id', '=', self.id)])
        for emp in all_emp:
            emp.export_employee_data(self)
        return True

    def export_payments(self):
        """ Export all the Payment methods of particular backend """
        all_pay_methods = self.env['account.payment'].search(
            [('payment_type', '=', 'inbound'), ('backend_id', '=', self.id)])
        for methods in all_pay_methods:
            methods.export_payment(self)
        return True

    def export_bills(self):
        """ Export all the Bills of particular backend """
        all_bill = self.env['account.move'].search(
            [('backend_id', '=', self.id), ('type', '=', 'in_invoice')])
        for bill in all_bill:
            bill.export_bill_data(self)
        return True

    def export_accounts(self):
        """ Export all the Account of particular backend """
        all_account = self.env['account.account'].search(
            [('backend_id', '=', self.id)])
        for acc in all_account:
            acc.export_account_data(self)
        return True

    def export_departments(self):
        """ Export all the Account of particular backend """
        all_departments = self.env['hr.department'].search(
            [('backend_id', '=', self.id)])
        for dep in all_departments:
            dep.export_department_data(self)
        return True

    def export_sales(self):
        """ Export all the Account of particular backend """
        all_sales = self.env['sale.order'].search(
            [('backend_id', '=', self.id)])
        for sale in all_sales:
            sale.export_sale_data(self)
        return True

    def export_tax(self):

        """ Export all tax the t of particular backend """
        all_tax = self.env['account.tax'].search(
            [('backend_id', '=', self.id)])
        for tax in all_tax:
            tax.export_tax_data(self)
        return True

    #############Mapping#################
    def map_employees(self):
        all_employees = self.env['hr.employee'].search([])
        for employee in all_employees:
            employee.update({'backend_id': self.id})
        return True

    def map_customers(self):
        all_customers = self.env['res.partner'].search([])
        for customer in all_customers:
            customer.update({'backend_id': self.id})
        return True

    def map_accounts(self):
        all_accounts = self.env['account.account'].search([])
        for account in all_accounts:
            account.update({'backend_id': self.id})
        return True

    def map_products(self):
        all_products = self.env['product.template'].search([])
        for product in all_products:
            product.update({'backend_id': self.id})
        return True

    def map_vendors(self):
        all_vendors = self.env['res.partner'].search([])
        for vendor in all_vendors:
            vendor.update({'backend_id': self.id})
        return True

    def map_sale_order(self):
        all_sale_order = self.env['sale.order'].search([])
        for sale in all_sale_order:
            sale.update({'backend_id': self.id})
        return True

    def map_purchase_order(self):
        all_purchases = self.env['purchase.order'].search([])
        for purchase in all_purchases:
            purchase.update({'backend_id': self.id})
        return True