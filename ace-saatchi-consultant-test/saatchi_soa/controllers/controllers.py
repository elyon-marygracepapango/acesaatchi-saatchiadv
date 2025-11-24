# -*- coding: utf-8 -*-
# from odoo import http


# class SaatchiSoa(http.Controller):
#     @http.route('/saatchi_soa/saatchi_soa', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/saatchi_soa/saatchi_soa/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('saatchi_soa.listing', {
#             'root': '/saatchi_soa/saatchi_soa',
#             'objects': http.request.env['saatchi_soa.saatchi_soa'].search([]),
#         })

#     @http.route('/saatchi_soa/saatchi_soa/objects/<model("saatchi_soa.saatchi_soa"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('saatchi_soa.object', {
#             'object': obj
#         })

