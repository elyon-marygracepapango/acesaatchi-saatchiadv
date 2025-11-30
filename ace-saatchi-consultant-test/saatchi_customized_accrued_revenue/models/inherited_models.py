# -*- coding: utf-8 -*-
"""
Inherited Model Extensions for Accrued Revenue
===============================================
Extends sale.order, account.move, account.move.line, and
account.general.ledger.report.handler to support accrued revenue functionality.
"""

from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError
from odoo.tools import SQL
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    """
    Sale Order Extension
    
    Adds custom fields and methods for:
    - CE status tracking
    - Approved estimates and invoiced amounts (billing & revenue)
    - Variance calculations
    - Accrual creation logic (normal, override, adjustment)
    """
    _inherit = "sale.order"
    
    # ========== Custom CE Fields ==========
    x_ce_status = fields.Selection(
        [
            ('for_client_signature', 'For Client Signature'),
            ('signed', 'Signed'),
            ('billable', 'Billable'),
            ('closed', 'Closed'),
            ('cancelled', 'Cancelled')
        ],
        default='for_client_signature',
        required=True,
        string='C.E. Status',
        tracking=True
    )

    x_job_number = fields.Char(
        string="Job Number"
    )


    related_accrued_revenue_count = fields.Integer(string="Related Accrued Revenue Count", compute="_compute_related_accrued_revenue_count")
    related_accrued_revenue_journal_items_count = fields.Integer(string="Related Accrued Revenue Journal Items Count", compute="_compute_related_accrued_revenue_journal_items_count")
    


    # ========== Accrual Collection Methods ==========
    
    @api.model
    def collect_potential_accruals(self, accrual_date, reversal_date):
        """
        Collect sale orders eligible for accrual creation
        
        Criteria:
        - state = 'sale'
        - x_ce_status in ['signed', 'billable']
        
        Args:
            accrual_date: Accrual period start date
            reversal_date: Accrual period end date
        
        Returns:
            tuple: (potential_sos, duplicate_sos)
        """
        potential = self.env['sale.order']
        duplicates = self.env['sale.order']

        eligible_sos = self.search([
            ('state', '=', 'sale'),
            ('x_ce_status', 'in', ['signed', 'billable']),
            ('x_ce_code', '!=', False)
        ])
        
        for so in eligible_sos:
            potential |= so
            
            existing = self.env['saatchi.accrued_revenue'].search([
                ('x_related_ce_id', '=', so.id),
                ('date', '>=', accrual_date),
                ('date', '<=', reversal_date),
                ('state', 'in', ['draft', 'accrued','reversed'])
            ], limit=1)
            
            if existing:
                duplicates |= so

        return potential, duplicates

    # ========== Wizard Action Methods ==========
    
    def action_open_wizard_create_accrued_revenue(self, records, special_case=False):
        """
        Open wizard to create accrued revenue for selected sale orders
        
        Args:
            records: Sale order recordset
            special_case: If True, enables scenario selection (Manual/Cancel/Adjustment)
        
        Returns:
            dict: Action to open wizard
        """
        accrual_date = self.env['saatchi.accrued_revenue']._default_accrual_date()
        reversal_date = self.env['saatchi.accrued_revenue']._default_reversal_date()
        
        wizard = self.env['saatchi.accrued_revenue.wizard'].create({
            'accrual_date': accrual_date,
            'reversal_date': reversal_date,
            'special_case_mode': special_case,
        })
        
        for record in records:
            if (record.x_ce_variance_revenue > 0 or special_case) and record.state == 'sale':
                existing = self.env['saatchi.accrued_revenue'].search([
                    ('x_related_ce_id', '=', record.id),
                    ('date', '>=', accrual_date),
                    ('date', '<=', reversal_date),
                    ('state', 'in', ['draft', 'accrued', 'reversed'])
                ])
                
                self.env['saatchi.accrued_revenue.wizard.line'].create({
                    'wizard_id': wizard.id,
                    'sale_order_id': record.id,
                    'amount_total': record.x_ce_variance_revenue,
                    'has_existing_accrual': bool(existing),
                    'existing_accrual_ids': [(6, 0, existing.ids)],
                    'create_accrual': True,
                })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Accrued Revenue'),
            'res_model': 'saatchi.accrued_revenue.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'views': [(False, 'form')],
            'target': 'new',
            'context': self.env.context,
        }

    # ========== Accrual Creation Methods ==========
    
    def _calculate_accrual_amount(self):
        """
        Calculate total accrual amount for this sale order
        
        Only processes Agency Charges category lines that have:
        - Delivered but not invoiced quantity (accrued_qty > 0)
        
        Returns:
            float: Total accrual amount
        """
        self.ensure_one()
        amount_total = 0
        
        for line in self.order_line:
            if line.display_type:
                continue
            
            if not self._is_agency_charges_category(line.product_template_id):
                continue
            
            accrued_qty = line.product_uom_qty - line.qty_invoiced
            if accrued_qty <= 0:
                continue
            
            accrued_amount = accrued_qty * line.price_unit
            amount_total += accrued_amount
        
        return amount_total

    def action_create_custom_accrued_revenue(self, is_override=False, accrual_date=False, reversal_date=False, is_adjustment=False, is_system_generated=True):
        """
        Create accrued revenue entry for this sale order
        
        Process:
        1. Validate SO state (skip if override=True)
        2. Create accrued revenue record
        3. Create lines based on type:
           - Normal/Override: Individual SO lines + Total Accrued (with auto-reversal)
           - Adjustment: Digital Income line + Total Accrued (NO auto-reversal)
        
        Args:
            is_override: If True, skip validation (Scenario 1: Manual Accrue)
            accrual_date: Custom accrual date
            reversal_date: Custom reversal date
            is_adjustment: If True, create adjustment entry (Scenario 3 - NO auto-reversal)
        
        Returns:
            int: Accrual record ID if successful, False otherwise
        """
        self.ensure_one()
        
        # Validate sale order state (skip if override or adjustment)
        if not is_override and not is_adjustment:
            if self.state != 'sale' or self.x_ce_status not in ['signed', 'billable']:
                _logger.warning(f"SO {self.name} does not meet accrual criteria")
                return False
        
        if not accrual_date:
            accrual_date = self.env['saatchi.accrued_revenue']._default_accrual_date()
        # if not reversal_date:
        #     reversal_date = self.env['saatchi.accrued_revenue']._default_reversal_date()
        
        # Create accrued revenue record
        accrued_revenue = self.env['saatchi.accrued_revenue'].create({
            'x_related_ce_id': self.id,
            'currency_id': self.currency_id.id,
            'date': accrual_date,
            'reversal_date': reversal_date,
            'is_adjustment_entry': is_adjustment,
            'x_accrual_system_generated': is_system_generated
        })
        
        if is_adjustment:
            # Scenario 3: Create adjustment entry (NO auto-reversal)
            result = self._create_adjustment_entry_lines(accrued_revenue)
        else:
            # Normal or Override: Create lines from SO (with auto-reversal)
            result = self._create_normal_accrual_lines(accrued_revenue)
        
        # Return the result (accrual ID or False)
        return result
    
    def _create_normal_accrual_lines(self, accrued_revenue):
        """
        Create normal accrual lines from SO lines
        
        Structure:
        - Credit lines: Revenue accounts (from SO lines)
        - Debit line: Total Accrued (accrual account)
        - Creates automatic reversal entry
        
        Args:
            accrued_revenue: The accrued revenue record
            
        Returns:
            int: Accrual record ID if successful, False otherwise
        """
        total_eligible_for_accrue = 0
        lines_created = 0
        
        _logger.info(f"Starting accrual creation for SO {self.name}")
        
        for line in self.order_line:
            if line.display_type:
                continue
            
            if not self._is_agency_charges_category(line.product_template_id):
                _logger.debug(f"Skipping line {line.name} - not Agency Charges category")
                continue
            
            accrued_qty = line.product_uom_qty - line.qty_invoiced
            if accrued_qty <= 0:
                _logger.debug(f"Skipping line {line.name} - no accrued qty (qty: {line.product_uom_qty}, invoiced: {line.qty_invoiced})")
                continue
            
            accrued_amount = accrued_qty * line.price_unit
            
            # Determine analytic distribution with fallback logic
            analytic_distribution = line.analytic_distribution or {}
            
            # Fallback to SO level analytic distribution
            if not analytic_distribution and hasattr(self, 'analytic_distribution') and self.analytic_distribution:
                analytic_distribution = self.analytic_distribution
            
            # Default to analytic account ID 2 if still no distribution found
            if not analytic_distribution:
                analytic_distribution = {2: 100}
                _logger.debug(f"Using default analytic account (ID: 2) for line {line.name}")
            
            income_account = line.product_id.property_account_income_id or \
                           line.product_id.categ_id.property_account_income_categ_id
            
            if not income_account:
                _logger.warning(f"No income account found for line {line.name} in SO {self.name}")
                continue
            
            self.env['saatchi.accrued_revenue_lines'].create({
                'accrued_revenue_id': accrued_revenue.id,
                'ce_line_id': line.id,
                'account_id': income_account.id,
                'label': f'{self.x_ce_code} - {line.name}',
                'credit': accrued_amount,
                'debit': 0.0,
                'currency_id': line.currency_id.id,
                'analytic_distribution': analytic_distribution,
            })
            
            total_eligible_for_accrue += accrued_amount
            lines_created += 1
            _logger.debug(f"Created line for {line.name}, amount: {accrued_amount}")
        
        if lines_created == 0:
            accrued_revenue.unlink()
            _logger.warning(f"No eligible lines found for accrual in SO {self.name}")
            return False
        
        # Create Total Accrued line (debit)
        self.env['saatchi.accrued_revenue_lines'].create({
            'accrued_revenue_id': accrued_revenue.id,
            'label': 'Total Accrued',
            'currency_id': self.currency_id.id,
            'account_id': accrued_revenue.accrual_account_id.id,
            'debit': 0.0,
            'credit': 0.0,
        })
        
        accrued_revenue.write({'ce_original_total_amount': total_eligible_for_accrue})
        
        _logger.info(f"✓ Created accrual ID {accrued_revenue.id} for SO {self.name} with {lines_created} lines, total: {total_eligible_for_accrue}")
        
        return accrued_revenue.id
    
    def _create_adjustment_entry_lines(self, accrued_revenue):
        """
        Create adjustment entry lines (Scenario 3)
        
        Structure (only 2 lines, NO auto-reversal):
        1. Dr. Digital Income (5787) - default calculated amount (user editable)
        2. Cr. Total Accrued (1210) - matches Digital Income amount
        
        This is a PERMANENT adjustment entry, NOT reversed automatically.
        
        Args:
            accrued_revenue: The accrued revenue record
            
        Returns:
            int: Accrual record ID if successful, False otherwise
        """
        # Calculate total accrual amount as default suggestion
        total_accrual_amount = self._calculate_accrual_amount()
        
        if total_accrual_amount <= 0:
            # Still create the entry but with 0 amount (user will fill in manually)
            total_accrual_amount = 0
            _logger.info(f"Creating adjustment entry for SO {self.name} with 0 default amount (user will edit)")
        
        # Get Digital Income account (ID: 5787)
        digital_income_account = accrued_revenue.digital_income_account_id
        if not digital_income_account:
            accrued_revenue.unlink()
            raise UserError(_("Digital Income account not configured. Please set it in the accrual settings."))
        
        # Get analytic distribution from SO
        analytic_distribution = {}
        if hasattr(self, 'analytic_distribution') and self.analytic_distribution:
            analytic_distribution = self.analytic_distribution
        
        # Line 1: Dr. Digital Income (user can edit this amount)
        self.env['saatchi.accrued_revenue_lines'].create({
            'accrued_revenue_id': accrued_revenue.id,
            'account_id': digital_income_account.id,
            'label': 'Digital Income - Adjustment',
            'debit': total_accrual_amount,
            'credit': 0.0,
            'currency_id': self.currency_id.id,
            'analytic_distribution': analytic_distribution,
        })
        
        # Line 2: Cr. Total Accrued (will be auto-calculated to match)
        self.env['saatchi.accrued_revenue_lines'].create({
            'accrued_revenue_id': accrued_revenue.id,
            'label': 'Total Accrued',
            'currency_id': self.currency_id.id,
            'account_id': accrued_revenue.accrual_account_id.id,
            'debit': 0.0,
            'credit': 0.0,
        })
        
        accrued_revenue.write({'ce_original_total_amount': total_accrual_amount})
        
        _logger.info(f"✓ Created adjustment entry for SO {self.name}, default amount: {total_accrual_amount} (NO auto-reversal)")
        
        return accrued_revenue.id

    def _is_agency_charges_category(self, product):
        """
        Check if product belongs to Agency Charges category or its children
        
        Args:
            product: product.template recordset
        
        Returns:
            bool: True if product is in Agency Charges category
        """
        if not product or not product.categ_id:
            return False
        
        current_categ = product.categ_id
        while current_categ:
            if current_categ.name.lower() == 'agency charges':
                return True
            current_categ = current_categ.parent_id
        
        return False

    def action_view_accrued_revenues(self):
        self.ensure_one()
        return {
            'name': 'Accrued Revenues',
            'type': 'ir.actions.act_window',
            'res_model': 'saatchi.accrued_revenue',
            'view_mode': 'list,form',
            'domain': [('x_related_ce_id', '=', self.id)],
            'context': {'default_x_related_ce_id': self.id},
        }

    def action_view_accrued_revenues_journal_items(self):
        self.ensure_one()
        list_view_id = self.env.ref('saatchi_customized_accrued_revenue.view_accrued_revenue_journal_items_list').id
        search_view_id = self.env.ref('saatchi_customized_accrued_revenue.view_account_move_line_accrued_revenue_filter').id
        return {
            'name': 'Accrued Revenues Journal Items',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'views': [(list_view_id, 'list')],
            'search_view_id': search_view_id,  # Add comma here!
            'domain': [('x_ce_code', '=', self.x_ce_code)],
            'context': {'journal_type': 'general', 'search_default_posted': 1},
        }

        
    def _compute_related_accrued_revenue_count(self):
        for record in self:
            record.related_accrued_revenue_count = self.env['saatchi.accrued_revenue'].search_count([
                ('x_related_ce_id', '=', record.id)
            ])

    def _compute_related_accrued_revenue_journal_items_count(self):
        for record in self:
            record.related_accrued_revenue_journal_items_count = self.env['account.move.line'].search_count([
                ('x_ce_code', '=', record.x_ce_code)
            ])
            
class AccountMove(models.Model):
    """
    Account Move Extension
    
    Adds fields to track accrued revenue-related journal entries.
    """
    _inherit = "account.move"
    
    x_related_custom_accrued_record = fields.Many2one(
        'saatchi.accrued_revenue',
        store=True,
        readonly=True,
        string="Related Accrued Revenue",
        help="Link to the accrued revenue record that generated this move"
    )
    
    x_remarks = fields.Char(
        string="Remarks",
        help="Additional remarks for this journal entry"
    )

    x_accrual_system_generated = fields.Boolean(
        string="System Generated",
        help="Indicates if this accrual was generated automatically by the system"
    )
    x_is_reversal = fields.Boolean(string="Is Reversal Entry?")
    
    x_is_accrued_entry = fields.Boolean(string="Is Accrued Entry?")

    x_type_of_entry = fields.Selection(
        selection=[
            ('reversal_system', 'Reversal Entry - System'),
            ('reversal_manual', 'Reversal Entry - Manual'),
            ('accrued_system', 'Accrued Entry - System'),
            ('accrued_manual', 'Accrued Entry - Manual'),
            ('adjustment_system', 'Adjustment Entry - System'),
            ('adjustment_manual', 'Adjustment Entry - Manual'),
        ],
        string="Entry Type",
        compute="_compute_entry_type",
        store=True,
        readonly=True
    )
    
    @api.depends('x_related_custom_accrued_record', 
                 'x_related_custom_accrued_record.is_adjustment_entry',
                 'x_accrual_system_generated',
                 'ref')
    def _compute_entry_type(self):
        """Determine entry type based on accrued revenue record and generation method"""
        for move in self:
            if not move.x_related_custom_accrued_record:
                move.x_type_of_entry = False
                continue
            
            # Determine if system or manual
            suffix = 'system' if move.x_accrual_system_generated else 'manual'
            
            # Determine entry type
            if move.x_related_custom_accrued_record.is_adjustment_entry:
                move.x_type_of_entry = f'adjustment_{suffix}'
            elif move.ref and 'Reversal' in move.ref:
                move.x_type_of_entry = f'reversal_{suffix}'
            else:
                move.x_type_of_entry = f'accrued_{suffix}'




class AccountMoveLine(models.Model):
    """
    Account Move Line Extension
    
    Adds custom fields for tracking CE-related information on journal entry lines.
    """
    _inherit = "account.move.line"

    x_ce_code = fields.Char(
        string="CE Code",
        help="Contract Estimate code from sale order"
    )

    x_sale_order = fields.Many2one(related='move_id.x_related_custom_accrued_record.x_related_ce_id')
    
    x_ce_date = fields.Date(
        string="CE Date",
        help="Contract Estimate date from sale order"
    )
    
    x_remarks = fields.Char(
        string="Remarks",
        help="Additional remarks for this journal entry line"
    )

    x_reference = fields.Char(
        string="Reference",
        related='move_id.ref'
    )
    
    x_is_reversal = fields.Boolean(
        string="Is Reversal Entry?",
        related='move_id.x_is_reversal')
    
    x_is_accrued_entry = fields.Boolean(
        string="Is Accrued Entry?",
        related='move_id.x_is_accrued_entry')
    
    x_is_adjustment_entry = fields.Boolean(
        string="Is Adjustment Entry?",
        related='move_id.x_is_accrued_entry')


    x_type_of_entry = fields.Selection(
        selection=[
            ('reversal_system', 'Reversal Entry - System'),
            ('reversal_manual', 'Reversal Entry - Manual'),
            ('accrued_system', 'Accrued Entry - System'),
            ('accrued_manual', 'Accrued Entry - Manual'),
            ('adjustment_system', 'Adjustment Entry - System'),
            ('adjustment_manual', 'Adjustment Entry - Manual'),
        ],
        string="Entry Type",
        related='move_id.x_type_of_entry',
        store=True,
        readonly=True
    )
    
    x_ce_status = fields.Selection(
        [
            ('for_client_signature', 'For Client Signature'),
            ('signed', 'Signed'),
            ('billable', 'Billable'),
            ('closed', 'Closed'),
            ('cancelled', 'Cancelled')
        ],
        string='C.E. Status',
        related='move_id.x_related_custom_accrued_record.ce_status'
    )


class GeneralLedgerCustomHandler(models.AbstractModel):
    """
    General Ledger Report Handler Extension
    
    Overrides the query to include currency_name in the General Ledger report.
    """
    _inherit = 'account.general.ledger.report.handler'

    def _get_query_amls(self, report, options, expanded_account_ids, offset=0, limit=None):
        """Override to add currency_name field to General Ledger query"""
        additional_domain = [('account_id', 'in', expanded_account_ids)] if expanded_account_ids is not None else None
        queries = []
        journal_name = self.env['account.journal']._field_to_sql('journal', 'name')
        
        for column_group_key, group_options in report._split_options_per_column_group(options).items():
            query = report._get_report_query(group_options, domain=additional_domain, date_scope='strict_range')
            account_alias = query.left_join(lhs_alias='account_move_line', lhs_column='account_id', rhs_table='account_account', rhs_column='id', link='account_id')
            account_code = self.env['account.account']._field_to_sql(account_alias, 'code', query)
            account_name = self.env['account.account']._field_to_sql(account_alias, 'name')
            account_type = self.env['account.account']._field_to_sql(account_alias, 'account_type')

            query = SQL(
                '''
                SELECT
                    account_move_line.id,
                    account_move_line.date,
                    MIN(account_move_line.date_maturity)    AS date_maturity,
                    MIN(account_move_line.name)             AS name,
                    MIN(account_move_line.ref)              AS ref,
                    MIN(account_move_line.company_id)       AS company_id,
                    MIN(account_move_line.account_id)       AS account_id,
                    MIN(account_move_line.payment_id)       AS payment_id,
                    MIN(account_move_line.partner_id)       AS partner_id,
                    MIN(account_move_line.currency_id)      AS currency_id,
                    MIN(currency.name)                      AS currency_name,
                    SUM(account_move_line.amount_currency)  AS amount_currency,
                    MIN(COALESCE(account_move_line.invoice_date, account_move_line.date)) AS invoice_date,
                    account_move_line.date                  AS date,
                    SUM(%(debit_select)s)                   AS debit,
                    SUM(%(credit_select)s)                  AS credit,
                    SUM(%(balance_select)s)                 AS balance,
                    MIN(move.name)                          AS move_name,
                    MIN(company.currency_id)                AS company_currency_id,
                    MIN(partner.name)                       AS partner_name,
                    MIN(move.move_type)                     AS move_type,
                    MIN(%(account_code)s)                   AS account_code,
                    MIN(%(account_name)s)                   AS account_name,
                    MIN(%(account_type)s)                   AS account_type,
                    MIN(journal.code)                       AS journal_code,
                    MIN(%(journal_name)s)                   AS journal_name,
                    MIN(full_rec.id)                        AS full_rec_name,
                    %(column_group_key)s                    AS column_group_key
                FROM %(table_references)s
                JOIN account_move move                      ON move.id = account_move_line.move_id
                %(currency_table_join)s
                LEFT JOIN res_company company               ON company.id = account_move_line.company_id
                LEFT JOIN res_partner partner               ON partner.id = account_move_line.partner_id
                LEFT JOIN res_currency currency             ON currency.id = account_move_line.currency_id
                LEFT JOIN account_journal journal           ON journal.id = account_move_line.journal_id
                LEFT JOIN account_full_reconcile full_rec   ON full_rec.id = account_move_line.full_reconcile_id
                WHERE %(search_condition)s
                GROUP BY account_move_line.id, account_move_line.date
                ORDER BY account_move_line.date, move_name, account_move_line.id
                ''',
                account_code=account_code,
                account_name=account_name,
                account_type=account_type,
                journal_name=journal_name,
                column_group_key=column_group_key,
                table_references=query.from_clause,
                currency_table_join=report._currency_table_aml_join(group_options),
                debit_select=report._currency_table_apply_rate(SQL("account_move_line.debit")),
                credit_select=report._currency_table_apply_rate(SQL("account_move_line.credit")),
                balance_select=report._currency_table_apply_rate(SQL("account_move_line.balance")),
                search_condition=query.where_clause,
            )
            queries.append(query)

        full_query = SQL(" UNION ALL ").join(SQL("(%s)", query) for query in queries)

        if offset:
            full_query = SQL('%s OFFSET %s ', full_query, offset)
        if limit:
            full_query = SQL('%s LIMIT %s ', full_query, limit)

        return full_query



class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    accrued_revenue_account_id = fields.Many2one(
        'account.account',
        string='Accrued Revenue Account',
        config_parameter='account.accrued_revenue_account_id',
        domain=[('deprecated', '=', False)],
        help='Default account for accrued revenues'
    )
    
    accrued_journal_id = fields.Many2one(
        'account.journal',
        string='Accrued Revenue Journal',
        config_parameter='account.accrued_journal_id',
        domain=[('type', '=', 'general')],
        help='Default journal for accrued revenue entries'
    )
    
    accrued_default_adjustment_account_id = fields.Many2one(
        'account.account',
        string='Default Accrual Adjustment Account',
        config_parameter='account.accrued_default_adjustment_account_id',
        domain=[('deprecated', '=', False)],
        help='Default account for accrual adjustments, Account used for adjustment entries (Dr. side)'
    )