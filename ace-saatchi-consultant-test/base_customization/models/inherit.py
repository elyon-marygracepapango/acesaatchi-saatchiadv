# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
class InheritSaleOrder(models.Model):
    _inherit = 'sale.order'
    
    x_client_product_ce_code = fields.Many2one(
        'base_customization.client_product_ce_co_line',  # Use the NEW separate model
        string="Client - Product CE Code"
    )

    x_job_description = fields.Char('Job Description')
    x_ce_code = fields.Char(compute="_compute_x_ce_code", string="Client CE Code", store=True)
    # x_ce_code = fields.Char( string="Client CE Code", store=True)



    x_alt_currency_amount = fields.Float(
        string="Alt Total Amount",
        digits=(12, 2),
        help="Alternative currency total computed from order lines",
        compute="_compute_alt_currency_amount",
        store=True,  # set to True if you need it stored
    )



    
    x_alt_currency_id = fields.Many2one(
        'res.currency',
        string="Alt Currency",
        default=lambda self: self._default_alt_currency_id(),
    )


    def write(self, vals):
        res = super().write(vals)
        # Only trigger when the alternate currency changes or always on save
        if 'x_alt_currency_id' in vals:
            self._apply_alt_currency_conversion()
        return res

    def _apply_alt_currency_conversion(self):
        """Update all order lines with fx_currency and converted price."""
        for record in self:
            alt_currency = record.x_alt_currency_id
            if not alt_currency:
                continue

            for line in record.order_line:
                line.fx_currency_id = alt_currency
                line.fx_price_unit = line.currency_id._convert(
                    line.price_unit,
                    alt_currency,
                    record.company_id or record.env.company,
                    record.date_order
                )
                
    def _default_alt_currency_id(self):
        """Logic:
        1️⃣ If order currency != company currency → use company currency.
        2️⃣ Else if order lines exist with fx_currency_id → use first fx_currency_id.
        3️⃣ Else fallback to USD.
        """
        # self.ensure_one()

        company_currency = self.company_id.currency_id
        order_currency = self.currency_id

        # case 1
        if order_currency and company_currency and order_currency != company_currency:
            return company_currency.id

        # case 2
        fx_currency = self.order_line.filtered(lambda l: l.fx_currency_id)[:1].fx_currency_id
        if fx_currency:
            return fx_currency.id

        # case 3
        try:
            usd_currency = self.env.ref('base.USD')
            return usd_currency.id
        except ValueError:
            return company_currency.id or False

    @api.depends('order_line.fx_price_unit', 'x_alt_currency_id', 'date_order')
    def _compute_alt_currency_amount(self):
        """Compute the total alt amount by converting fx_price_unit to alt_currency."""
        for order in self:
            total = 0.0
            alt_currency = order.x_alt_currency_id or order.company_id.currency_id
    
            for line in order.order_line:
                fx_currency = line.fx_currency_id or order.currency_id
                fx_price = line.fx_price_unit or 0.0
    
                total += fx_currency._convert(
                    fx_price * line.product_uom_qty,
                    alt_currency,
                    order.company_id,
                    order.date_order or fields.Date.today()
                )
            order.x_alt_currency_amount = total



    @api.depends('x_client_product_ce_code')
    def _compute_x_ce_code(self):
        for record in self:
            if record.x_client_product_ce_code:
                ce_code = f'{record.x_client_product_ce_code.x_ce_product_code}{record.name}'
                record.x_ce_code = ce_code
            else:
                record.x_ce_code = ''
        
    @api.onchange('partner_id')
    def _onchange_partner_copy_ce_codes(self):
        """Copy CE codes from master when partner changes"""
        if self.partner_id:
            # Find master CE codes for this partner
            master_lines = self.env['base_customization.client_product_ce_co_line'].search([
                ('x_client_product_ce_co_id.x_partner_id', '=', self.partner_id.id)
            ])
            
            # Create copies for this sale order (command 5 clears, command 0 creates)
            line_vals = []
            for master_line in master_lines:
                line_vals.append((0, 0, {
                    'x_product_id': master_line.x_product_id.id,
                    'x_ce_product_code': master_line.x_ce_product_code,
                }))
            
            self.x_client_product_ce_code = [(5, 0, 0)] + line_vals  # Clear and add new
        else:
            self.x_client_product_ce_code = [(5, 0, 0)]  # Clear all

class InheritSaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    
    fx_currency_id = fields.Many2one(
        'res.currency', 
        string="Alt Currency",
        default=lambda self: self.env.ref('base.USD', raise_if_not_found=False)
    )
    fx_price_unit = fields.Float(
        string="Alt Unit Price",
        help="Unit price in foreign exchange currency"
    )
    
    # Hidden field to track which field was last edited
    _last_edited_price_field = fields.Char(store=False)
    
    @api.model_create_multi
    def create(self, vals_list):
        """Auto-compute fx_price_unit when creating order lines"""
        lines = super(InheritSaleOrderLine, self).create(vals_list)
        for line in lines:
            if line.price_unit and line.fx_currency_id and not line.fx_price_unit:
                company_currency = line.order_id.company_id.currency_id or self.env.company.currency_id
                if company_currency and company_currency != line.fx_currency_id:
                    line.fx_price_unit = company_currency._convert(
                        line.price_unit,
                        line.fx_currency_id,
                        line.order_id.company_id or self.env.company,
                        line.order_id.date_order or fields.Date.today()
                    )
                elif company_currency == line.fx_currency_id:
                    line.fx_price_unit = line.price_unit
        return lines
    
    @api.onchange('price_unit', 'fx_currency_id')
    def _onchange_price_unit_to_fx(self):
        """Convert price_unit (order line currency) to fx_price_unit"""
        # Mark that price_unit was edited
        self._last_edited_price_field = 'price_unit'

        
        if self.price_unit and self.fx_currency_id:
            # Use the sale order line's currency_id (typically pricelist currency)
            line_currency = self.currency_id
            if line_currency and line_currency != self.fx_currency_id:
                # Convert from line currency to FX currency
                self.fx_price_unit = line_currency._convert(
                    self.price_unit,
                    self.fx_currency_id,
                    self.order_id.company_id or self.env.company,
                    self.order_id.date_order or fields.Date.today()
                )
            elif line_currency == self.fx_currency_id:
                self.fx_price_unit = self.price_unit
    
    @api.onchange('fx_price_unit')
    def _onchange_fx_price_unit_to_price(self):
        """Convert fx_price_unit to price_unit (order line currency)"""
        # Only convert if fx_price_unit was the last field edited by user
        # This prevents the chain reaction when price_unit triggers fx_price_unit change
        if self._last_edited_price_field == 'price_unit':
            # Reset the flag
            self._last_edited_price_field = None
            return
        
        # Mark that fx_price_unit was edited
        self._last_edited_price_field = 'fx_price_unit'
        
        if self.fx_price_unit and self.fx_currency_id:
            # Use the sale order line's currency_id (typically pricelist currency)
            line_currency = self.currency_id
            if line_currency and line_currency != self.fx_currency_id:
                # Convert from FX currency to line currency
                self.price_unit = self.fx_currency_id._convert(
                    self.fx_price_unit,
                    line_currency,
                    self.order_id.company_id or self.env.company,
                    self.order_id.date_order or fields.Date.today()
                )
            elif line_currency == self.fx_currency_id:
                self.price_unit = self.fx_price_unit



class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    x_alt_currency_amount = fields.Float(
        string="Alt Total Amount",
        digits=(12, 2),
        help="Alternative currency total computed from order lines",
        compute="_compute_alt_currency_amount",
        store=True,  # set to True if you need it stored
    )

    x_alt_currency_id = fields.Many2one(
        'res.currency',
        string="Alt Currency",
        default=lambda self: self._default_alt_currency_id(),
    )


    def write(self, vals):
        res = super().write(vals)
        # Only trigger when the alternate currency changes or always on save
        if 'x_alt_currency_id' in vals:
            self._apply_alt_currency_conversion()
        return res

    def _apply_alt_currency_conversion(self):
        """Update all order lines with fx_currency and converted price."""
        for record in self:
            alt_currency = record.x_alt_currency_id
            if not alt_currency:
                continue

            for line in record.order_line:
                line.fx_currency_id = alt_currency
                line.fx_price_unit = line.currency_id._convert(
                    line.price_unit,
                    alt_currency,
                    record.company_id or record.env.company,
                    record.date_order
                )
                
    def _default_alt_currency_id(self):
        """Logic:
        1️⃣ If order currency != company currency → use company currency.
        2️⃣ Else if order lines exist with fx_currency_id → use first fx_currency_id.
        3️⃣ Else fallback to USD.
        """
        # self.ensure_one()

        company_currency = self.company_id.currency_id
        order_currency = self.currency_id

        # case 1
        if order_currency and company_currency and order_currency != company_currency:
            return company_currency.id

        # case 2
        fx_currency = self.order_line.filtered(lambda l: l.fx_currency_id)[:1].fx_currency_id
        if fx_currency:
            return fx_currency.id

        # case 3
        try:
            usd_currency = self.env.ref('base.USD')
            return usd_currency.id
        except ValueError:
            return company_currency.id or False

    @api.depends('order_line.fx_price_unit', 'x_alt_currency_id', 'date_order')
    def _compute_alt_currency_amount(self):
        """Compute the total alt amount by converting fx_price_unit to alt_currency."""
        for order in self:
            total = 0.0
            alt_currency = order.x_alt_currency_id or order.company_id.currency_id
    
            for line in order.order_line:
                fx_currency = line.fx_currency_id or order.currency_id
                fx_price = line.fx_price_unit or 0.0
    
                total += fx_currency._convert(
                    fx_price * line.product_uom_qty,
                    alt_currency,
                    order.company_id,
                    order.date_order or fields.Date.today()
                )
            order.x_alt_currency_amount = total

class InheritPurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'
    
    fx_currency_id = fields.Many2one(
        'res.currency', 
        string="Alt Currency",
        default=lambda self: self.env.ref('base.USD', raise_if_not_found=False)
    )
    fx_price_unit = fields.Float(
        string="Alt Unit Price",
        help="Unit price in foreign exchange currency"
    )
    
    # Hidden field to track which field was last edited
    _last_edited_price_field = fields.Char(store=False)
    
    @api.model_create_multi
    def create(self, vals_list):
        """Auto-compute fx_price_unit when creating order lines"""
        lines = super(InheritPurchaseOrderLine, self).create(vals_list)
        for line in lines:
            if line.price_unit and line.fx_currency_id and not line.fx_price_unit:
                # Use the purchase order line's currency_id
                line_currency = line.currency_id
                if line_currency and line_currency != line.fx_currency_id:
                    line.fx_price_unit = line_currency._convert(
                        line.price_unit,
                        line.fx_currency_id,
                        line.order_id.company_id or self.env.company,
                        line.order_id.date_order or fields.Date.today()
                    )
                elif line_currency == line.fx_currency_id:
                    line.fx_price_unit = line.price_unit
        return lines
    
    @api.onchange('price_unit', 'fx_currency_id')
    def _onchange_price_unit_to_fx(self):
        """Convert price_unit (order line currency) to fx_price_unit"""
        # Mark that price_unit was edited
        self._last_edited_price_field = 'price_unit'
        
        if self.price_unit and self.fx_currency_id:
            # Use the purchase order line's currency_id
            line_currency = self.currency_id
            if line_currency and line_currency != self.fx_currency_id:
                # Convert from line currency to FX currency
                self.fx_price_unit = line_currency._convert(
                    self.price_unit,
                    self.fx_currency_id,
                    self.order_id.company_id or self.env.company,
                    self.order_id.date_order or fields.Date.today()
                )
            elif line_currency == self.fx_currency_id:
                self.fx_price_unit = self.price_unit
    
    @api.onchange('fx_price_unit')
    def _onchange_fx_price_unit_to_price(self):
        """Convert fx_price_unit to price_unit (order line currency)"""
        # Only convert if fx_price_unit was the last field edited by user
        # This prevents the chain reaction when price_unit triggers fx_price_unit change
        if self._last_edited_price_field == 'price_unit':
            # Reset the flag
            self._last_edited_price_field = None
            return
        
        # Mark that fx_price_unit was edited
        self._last_edited_price_field = 'fx_price_unit'
        
        if self.fx_price_unit and self.fx_currency_id:
            # Use the purchase order line's currency_id
            line_currency = self.currency_id
            if line_currency and line_currency != self.fx_currency_id:
                # Convert from FX currency to line currency
                self.price_unit = self.fx_currency_id._convert(
                    self.fx_price_unit,
                    line_currency,
                    self.order_id.company_id or self.env.company,
                    self.order_id.date_order or fields.Date.today()
                )
            elif line_currency == self.fx_currency_id:
                self.price_unit = self.fx_price_unit




class AccountMove(models.Model):
    _inherit = 'account.move'
    
    currency_display = fields.Char(
        related='currency_id.name',
        string='Currency',
        store=True,
        readonly=True
    )

    x_related_so = fields.Many2one('sale.order', compute="_compute_related_so", store=True)

    x_alt_currency_amount = fields.Float(
        string="Alt Total Amount",
        digits=(12, 2),
        help="Alternative currency total computed from order lines",
        compute="_compute_alt_currency_amount",
        store=True,  # set to True if you need it stored
    )



    x_alt_currency_id = fields.Many2one(
        'res.currency',
        related='x_related_so.x_alt_currency_id'
    )


    @api.model
    def create(self, vals):
        record = super().create(vals)
        record._apply_alt_currency_conversion()
        return record
    
    @api.depends('invoice_line_ids', 'state')
    def _compute_related_so(self):
        for record in self:
            record.x_related_so = False
            # for line in record.invoice_line_ids:
            #     if line.sale_line_ids:
            sale_order = record.invoice_line_ids.mapped('sale_line_ids.order_id')[:1] if record.invoice_line_ids else False
            record.x_related_so = sale_order
                
                
    def _apply_alt_currency_conversion(self):
        """Update all order lines with fx_currency and converted price."""
        for record in self:
            alt_currency = record.x_alt_currency_id
            if not alt_currency or not record.x_related_so:
                continue

            for line in record.invoice_line_ids:
                line.fx_currency_id = alt_currency
                line.fx_price_unit = line.currency_id._convert(
                    line.price_unit,
                    alt_currency,
                    record.company_id or record.env.company,
                    record.x_related_so.date_order
                )
                


    @api.depends('invoice_line_ids.fx_price_unit', 'invoice_line_ids.fx_currency_id', 'state')
    def _compute_alt_currency_amount(self):
        """Compute the total alt amount by converting fx_price_unit to alt_currency."""
        for record in self:
            total = 0.0
            alt_currency = record.x_alt_currency_id or record.company_id.currency_id

            if not record.x_alt_currency_id:
                record.x_alt_currency_amount = 0
                continue
                
            for line in record.invoice_line_ids:
                fx_currency = line.fx_currency_id or record.currency_id
                fx_price = line.fx_price_unit or 0.0
    
                total += fx_currency._convert(
                    fx_price * line.quantity,
                    alt_currency,
                    record.company_id,
                    record.x_related_so.date_order or fields.Date.today()
                )
            record.x_alt_currency_amount = total
        
class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    
    currency_display = fields.Char(
        related='currency_id.name',
        string='Currency',
        store=True,
        readonly=True
    )

    fx_currency_id = fields.Many2one(
        'res.currency', 
        string="Alt Currency",
        related='move_id.x_alt_currency_id'
    )
    fx_price_unit = fields.Float(
        string="Alt Unit Price",
        help="Unit price in foreign exchange currency"
    )


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'
        
    def get_button_approvers(self):
        """
        Returns the approvers configured in Studio approval button
        :return: recordset of res.users
        """
        self.ensure_one()
        
        approvers = self.env['res.users']
        
        # Method 1: Get from approval entries (if approval process has started)
        try:
            entries = self.env['studio.approval.entry'].search([
                ('res_id', '=', self.id),
                ('model', '=', 'purchase.order')
            ])
            if entries:
                approvers = entries.mapped('user_id')
                if approvers:
                    return approvers
        except:
            pass
        
        # Method 2: Get from approval rules configuration
        try:
            # Get the model record for purchase.order
            model_rec = self.env['ir.model'].search([
                ('model', '=', 'purchase.order')
            ], limit=1)
            
            if model_rec:
                # Find applicable approval rules
                rules = self.env['studio.approval.rule'].search([
                    ('model_id', '=', model_rec.id),
                    ('active', '=', True)
                ])
                
                for rule in rules:
                    # Check if rule applies to this record based on domain
                    if rule.domain:
                        try:
                            from odoo.tools.safe_eval import safe_eval
                            domain = safe_eval(rule.domain)
                            # Check if this record matches the domain
                            matching = self.search(domain + [('id', '=', self.id)])
                            if not matching:
                                continue
                        except Exception as e:
                            _logger.warning(f"Error evaluating domain for rule {rule.id}: {e}")
                            continue
                    
                    # Get approvers from the rule via studio.approval.rule.approver
                    rule_approvers = self.env['studio.approval.rule.approver'].search([
                        ('rule_id', '=', rule.id)
                    ])
                    
                    for rule_approver in rule_approvers:
                        if rule_approver.user_id:
                            approvers |= rule_approver.user_id
                        if hasattr(rule_approver, 'group_id') and rule_approver.group_id:
                            approvers |= rule_approver.group_id.users
                            
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning(f"Could not fetch approval rules: {e}")
        
        return approvers



class HrLeave(models.Model):
    _inherit = 'hr.leave'


    def _get_responsible_for_approval(self):
        self.ensure_one()
        responsible = self.env['res.users']
        
        # SWAP: HR OFFICER FIRST (confirm state)
        if self.validation_type == 'hr' or (self.validation_type == 'both' and self.state == 'confirm'):
            if self.holiday_status_id.responsible_ids:
                responsible = self.holiday_status_id.responsible_ids
        
        # SWAP: MANAGER SECOND (validate1 state)
        elif self.validation_type == 'manager' or (self.validation_type == 'both' and self.state == 'validate1'):
            if self.employee_id.leave_manager_id:
                responsible = self.employee_id.leave_manager_id
            elif self.employee_id.parent_id.user_id:
                responsible = self.employee_id.parent_id.user_id
        
        return responsible