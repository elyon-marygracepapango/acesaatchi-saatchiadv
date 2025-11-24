# -*- coding: utf-8 -*-
# from odoo import http


# class StudioCustomization(http.Controller):
#     @http.route('/studio_customization/studio_customization', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/studio_customization/studio_customization/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('studio_customization.listing', {
#             'root': '/studio_customization/studio_customization',
#             'objects': http.request.env['studio_customization.studio_customization'].search([]),
#         })

#     @http.route('/studio_customization/studio_customization/objects/<model("studio_customization.studio_customization"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('studio_customization.object', {
#             'object': obj
#         })

