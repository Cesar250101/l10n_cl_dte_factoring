# -*- coding: utf-8 -*-
{
    "name": """Chile - Web Services Cesión de Documentos Tributarios Electrónicos\
    """,
    'version': '9.0.5.0.1',
    'category': 'Localization/Chile',
    'sequence': 12,
    'author':  'Daniel Santibáñez Polanco',
    'website': 'https://globalresponse.cl',
    'license': 'AGPL-3',
    'summary': '',
    'description': """
Chile: Cesión de Documentos Tributarios.
""",
    'depends': [
        'l10n_cl_dte',
    ],
    'data': [
        'views/invoice_view.xml',
        #'views/partner_view.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
