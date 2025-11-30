# -*- coding: utf-8 -*-
{
    'name': "Saatchi Customized Accrued Revenue",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "Mark Angelo S. Templanza / Elyon IT Consultant",
    'website': "https://www.elyon-solutions.com/",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base','sale', 'account'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/views.xml',
        'views/inherited_views.xml',
        'wizard/accrued_revenue_duplicate_checker_wizard_view.xml',
        'data/data.xml'
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],

    'assets': {
        'web.assets_backend': [
            'saatchi_customized_accrued_revenue/static/src/js/sync_js_button.js',
            'saatchi_customized_accrued_revenue/static/src/js/unfold_js_button.js',
            'saatchi_customized_accrued_revenue/static/src/xml/sync_js_button.xml',
            'saatchi_customized_accrued_revenue/static/src/xml/unfold_all_list.xml',
        ]
    }
}

