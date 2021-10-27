# -*- coding: utf-8 -*-
{
    'name': "Quickbooks Odoo Connector",

    'summary': """
         QuickBooks Odoo Connector Odoo Quickbooks Desktop Odoo QuickBooks Bundle Connector Odoo Quickbooks Odoo quickbooks integration   QuickBooks Credit Memo Quickbooks reports odoo quickbooks connect accounting app accounting reports """,

    'description': """
        - Export and import data to and from Quickbooks.
        - For enabling Chart Of Accounts, activate accounting features by enabling the option in user settings.

    """,

    'author': "Techspawn Solutions",
    'website': "http://www.techspawn.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/openerp/addons/base/module/module_data.xml
    # for the full list
    'license':'OPL-1',
    'category': 'custom',
    'version': '1.0.0',

    # any module necessary for this one to work correctly
    'depends': ['base', 'sale', 'sale_management', 'stock', 'purchase', 'hr'],
    'price': 149.00,
    'currency': 'EUR',

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'security/security_view.xml',
        'views/backend.xml',
        'views/customer_vendor.xml',
        'views/product_quick.xml',
        'views/payment_term_view.xml',
        'views/quick_account.xml',
        'views/employee_form.xml',
        'views/sync_all.xml',
        'views/schedule_refresh_token.xml',
    ],
    'external_dependencies': {
        'python': ['requests_oauthlib'],
    },
    
    "images": ['static/description/Quickbooks_New_V13.gif'],
    'installable': True,
}
