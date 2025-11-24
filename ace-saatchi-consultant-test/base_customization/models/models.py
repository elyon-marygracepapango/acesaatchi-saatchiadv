# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class ClientProductCeCode(models.Model):
    _name = 'base_customization.client_product_ce_code'
    _description = 'Client Product CE Code'
    _inherit = ['mail.thread']
    _rec_name = 'name'
    
    name = fields.Char(string="Name", compute='_compute_name', store=True)
    x_partner_id = fields.Many2one('res.partner', string="Contact / Customer", required=True)
    
    x_client_product_ce_co_line_ids = fields.One2many(
        'base_customization.client_product_ce_co_line',
        'x_client_product_ce_co_id',
        string="Client - Product CE Code"
    )


    @api.depends('x_partner_id')
    def _compute_name(self):
        for record in self:
            if record.x_partner_id:
                record.name = f"{record.x_partner_id.name} | {record.x_product_id.name}"
            else:
                record.name = "CE Code | Blank"
                
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'x_partner_id' in vals:
                existing = self.search([
                    ('x_partner_id', '=', vals['x_partner_id'])
                ], limit=1)
                if existing:
                    partner_name = self.env['res.partner'].browse(vals['x_partner_id']).name
                    raise ValidationError(
                        f"A CE Code record already exists for customer '{partner_name}'. "
                        f"\nPlease edit the existing record instead."
                    )
        return super(ClientProductCeCode, self).create(vals_list)
    
    def write(self, vals):
        if 'x_partner_id' in vals:
            existing = self.search([
                ('x_partner_id', '=', vals['x_partner_id']),
                ('id', '!=', self.id)
            ], limit=1)
            if existing:
                partner_name = self.env['res.partner'].browse(vals['x_partner_id']).name
                raise ValidationError(
                    f"A CE Code record already exists for customer '{partner_name}'. "
                    f"\nPlease edit the existing record instead."
                )
        return super(ClientProductCeCode, self).write(vals)


class ClientProductCELine(models.Model):
    _name = 'base_customization.client_product_ce_co_line'
    _description = 'Client Product CE Line (Master)'
    _rec_name = 'name'
    
    name = fields.Char(string="Name", compute='_compute_name', store=True)
    x_client_product_ce_co_id = fields.Many2one(
        'base_customization.client_product_ce_code',
        string="Client Product CE Code",
        ondelete='cascade'
    )
    x_product_id = fields.Many2one('product.template', string="Product", required=True)
    x_ce_product_code = fields.Char(string="CE Code", required=True)
    
    @api.depends('x_product_id', 'x_ce_product_code')
    def _compute_name(self):
        for record in self:
            if record.x_product_id and record.x_ce_product_code:
                record.name = f"{record.x_product_id.name} | {record.x_ce_product_code}"
            elif record.x_product_id:
                record.name = record.x_product_id.name
            elif record.x_ce_product_code:
                record.name = record.x_ce_product_code
            else:
                record.name = "New Line"


# NEW: Separate model for Sale Order lines (transactional copy)
class SaleOrderCELine(models.Model):
    _name = 'base_customization.sale_order_ce_line'
    _description = 'Sale Order CE Line (Copy)'
    
    sale_order_id = fields.Many2one('sale.order', string="Sale Order", ondelete='cascade')
    x_product_id = fields.Many2one('product.template', string="Product", required=True)
    x_ce_product_code = fields.Char(string="CE Code", required=True)