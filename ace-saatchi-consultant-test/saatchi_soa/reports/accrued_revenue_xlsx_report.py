from odoo import models
import datetime
from xlsxwriter.workbook import Workbook
from odoo.exceptions import ValidationError, UserError
from dateutil.relativedelta import relativedelta
import logging
from collections import defaultdict

_logger = logging.getLogger(__name__)

class AccruedRevenueXLSX(models.AbstractModel):
    _name = 'report.accrued_revenue_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Accrued Revenue XLSX Report'

    def _get_accrued_revenue_account_id(self):
        """Get accrued revenue account ID with fallback"""
        try:
            account_id = int(self.env['ir.config_parameter'].sudo().get_param(
                'account.accrued_revenue_account_id',
                default='0'
            ) or 0)
            
            if account_id:
                account = self.env['account.account'].sudo().browse(account_id)
                if account.exists() and not account.deprecated:
                    return account_id
            
            # Fallback: Find miscellaneous income account
            misc_account = self.env['account.account'].sudo().search([
                ('account_type', '=', 'income_other'),
                ('deprecated', '=', False),
                ('company_id', '=', self.env.company.id)
            ], limit=1)
            
            return misc_account.id if misc_account else 0
            
        except (ValueError, TypeError):
            return 0

    def _define_formats(self, workbook):
        """Define and return format objects."""
        base_font = {'font_name': 'Calibri', 'font_size': 10}
        
        # Title formats
        title_format = workbook.add_format({
            **base_font,
            'bold': True,
            'font_size': 11
        })
        
        # Section header format with borders
        section_header_format = workbook.add_format({
            **base_font,
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 2
        })
        
        # Section header format without borders (for empty cells)
        section_header_no_border = workbook.add_format({
            **base_font,
            'bold': True,
            'align': 'center',
            'valign': 'vcenter'
        })
        
        # Column header format with thick borders
        column_header_format = workbook.add_format({
            **base_font,
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 2
        })
        
        # Normal cell format with borders
        normal_format = workbook.add_format({
            **base_font,
            'align': 'left',
            'valign': 'vcenter',
            'border': 1
        })
        
        # Centered cell format with borders
        centered_format = workbook.add_format({
            **base_font,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1
        })
        
        # Date cell format with borders
        date_format = workbook.add_format({
            **base_font,
            'num_format': 'mm/dd/yyyy',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1
        })
        
        # Currency format with borders (with dash for zero)
        currency_format = workbook.add_format({
            **base_font,
            'num_format': '#,##0.00;-#,##0.00;"-"',
            'align': 'right',
            'valign': 'vcenter',
            'border': 1
        })
        
        # Currency format with parentheses for negatives with borders (with dash for zero)
        currency_negative_format = workbook.add_format({
            **base_font,
            'num_format': '#,##0.00;(#,##0.00);"-"',
            'align': 'right',
            'valign': 'vcenter',
            'border': 1
        })
        
        return {
            'title': title_format,
            'section_header': section_header_format,
            'section_header_no_border': section_header_no_border,
            'column_header': column_header_format,
            'normal': normal_format,
            'centered': centered_format,
            'date': date_format,
            'currency': currency_format,
            'currency_negative': currency_negative_format
        }

    def _determine_accrual_months(self, lines):
        """Determine ALL accrual months based on accrual dates"""
        accrual_months = set()
        
        # Collect months from accrual dates
        for line in lines:
            if line.x_type_of_entry in ['accrued_system', 'accrued_manual'] and line.date:
                # Accrual date month IS the accrual month
                accrual_month = line.date.replace(day=1)
                accrual_months.add(accrual_month)
        
        # If no accruals found, collect from reversal dates
        if not accrual_months:
            for line in lines:
                if line.x_type_of_entry in ['reversal_system', 'reversal_manual'] and line.date:
                    accrual_month = line.date.replace(day=1)
                    accrual_months.add(accrual_month)
        
        # If still empty, fallback to today
        if not accrual_months:
            accrual_months.add(datetime.date.today().replace(day=1))
        
        # Return sorted list (oldest to newest)
        return sorted(list(accrual_months))

    def _group_lines_by_ce(self, lines, accrual_month):
        """Group account.move.line records by partner and CE code for a specific month"""
        grouped = defaultdict(lambda: defaultdict(lambda: {
            'ce_date': None,
            'description': '',
            'year': None,
            'ce_status': '',
            'lines': []
        }))
        
        # Filter lines for this specific accrual month
        accrual_month_end = (accrual_month + relativedelta(months=1)) - relativedelta(days=1)
        
        # Include lines that are:
        # 1. Reversals dated on the 1st of accrual_month
        # 2. Accruals/Adjustments dated within accrual_month
        month_lines = []
        for line in lines:
            if not line.date:
                continue
            
            # Reversal entries dated in accrual month (typically 1st)
            if line.x_type_of_entry in ['reversal_system', 'reversal_manual']:
                if line.date.month == accrual_month.month and line.date.year == accrual_month.year:
                    month_lines.append(line)
            # Accrual/Adjustment entries dated within accrual month
            elif line.x_type_of_entry in ['accrued_system', 'accrued_manual', 'adjustment_system', 'adjustment_manual']:
                if accrual_month <= line.date <= accrual_month_end:
                    month_lines.append(line)
        
        for line in month_lines:
            partner_name = line.partner_id.name.upper() if line.partner_id and line.partner_id.name else 'UNKNOWN'
            ce_code = line.x_ce_code.upper() if line.x_ce_code else 'NO_CE'
            
            # Store line for processing
            grouped[partner_name][ce_code]['lines'].append(line)
            
            # Capture CE-level fields (use first non-empty value found)
            if line.x_ce_date and not grouped[partner_name][ce_code]['ce_date']:
                grouped[partner_name][ce_code]['ce_date'] = line.x_ce_date
                grouped[partner_name][ce_code]['year'] = line.x_ce_date.year
            
            if line.move_id and line.move_id.x_related_custom_accrued_record and not grouped[partner_name][ce_code]['description']:
                desc = line.move_id.x_related_custom_accrued_record.ce_job_description or ''
                grouped[partner_name][ce_code]['description'] = desc.upper()
            
            if line.x_ce_status and not grouped[partner_name][ce_code]['ce_status']:
                var = line._fields['x_ce_status'].selection(line)
                ce_status = dict(var).get(line.x_ce_status)
                grouped[partner_name][ce_code]['ce_status'] = ce_status.upper()
        
        return grouped

    def _calculate_amounts_by_type(self, lines, accrual_month):
        """Calculate amounts for each entry type category"""
        amounts = {
            'system_reversal': 0,
            'system_accrual': 0,
            'manual_reversal': 0,
            'manual_reaccrual': 0,
            'manual_adjustment': 0
        }
        
        # Accrual month date range
        accrual_month_end = (accrual_month + relativedelta(months=1)) - relativedelta(days=1)
        
        for line in lines:
            if not line.date:
                continue
            
            # Calculate net amount (debit - credit)
            net_amount = (line.debit or 0) - (line.credit or 0)
            
            # Categorize based on type and date
            if line.x_type_of_entry == 'reversal_system':
                # Reversals dated on the 1st of accrual month
                if line.date.month == accrual_month.month and line.date.year == accrual_month.year:
                    amounts['system_reversal'] += net_amount
            
            elif line.x_type_of_entry == 'accrued_system':
                # Accruals dated within the accrual month
                if accrual_month <= line.date <= accrual_month_end:
                    amounts['system_accrual'] += net_amount
            
            elif line.x_type_of_entry == 'reversal_manual':
                # Manual reversals dated on the 1st of accrual month
                if line.date.month == accrual_month.month and line.date.year == accrual_month.year:
                    amounts['manual_reversal'] += net_amount
            
            elif line.x_type_of_entry == 'accrued_manual':
                # Manual re-accruals dated within the accrual month
                if accrual_month <= line.date <= accrual_month_end:
                    amounts['manual_reaccrual'] += net_amount
            
            elif line.x_type_of_entry in ['adjustment_system', 'adjustment_manual']:
                # All adjustments within the accrual month
                if accrual_month <= line.date <= accrual_month_end:
                    amounts['manual_adjustment'] += net_amount
        
        return amounts

    def generate_xlsx_report(self, workbook, data, lines):
        """Main report generation method."""
        accrued_account_id = self._get_accrued_revenue_account_id()
        if not accrued_account_id:
            raise UserError("Accrued Revenue account not configured. Please set it in system parameters.")
        
        filtered_lines = lines.filtered(lambda l: l.account_id.id == accrued_account_id)
        
        if not filtered_lines:
            raise UserError("No accrued revenue entries found for the selected records.")
        
        formats = self._define_formats(workbook)
        accrual_months = self._determine_accrual_months(filtered_lines)
        
        for accrual_month in accrual_months:
            self._generate_month_sheets(workbook, formats, filtered_lines, lines, accrual_month, accrued_account_id)
        
        return True
    
    def _generate_month_sheets(self, workbook, formats, filtered_lines, all_lines, accrual_month, accrued_account_id):
        """Generate all sheets for a specific accrual month"""
        prev_month = accrual_month - relativedelta(months=1)
        
        # Get last day of previous month and current month
        prev_month_last_day = (accrual_month - relativedelta(days=1)).day
        accrual_month_last_day = ((accrual_month + relativedelta(months=1)) - relativedelta(days=1)).day
        
        # Format month names
        prev_month_abbr = prev_month.strftime('%b').upper()
        accrual_month_abbr = accrual_month.strftime('%b').upper()
        
        # Format full month name and year for title
        accrual_month_full = accrual_month.strftime('%B %Y').upper()
        
        # Report date
        report_date = accrual_month.strftime('%-m/%-d/%Y')
        
        # Group lines by client and CE# for this specific month
        grouped_data = self._group_lines_by_ce(filtered_lines, accrual_month)
        
        # Skip this month if no data
        if not grouped_data:
            return
        
        # Create main sheet with formatted name (e.g., "November 2025")
        sheet_name_main = accrual_month.strftime('%B %Y')
        sheet = workbook.add_worksheet(sheet_name_main)
        
        # Set column widths
        sheet.set_column(0, 0, 30)   # CLIENT
        sheet.set_column(1, 1, 15)   # CE#
        sheet.set_column(2, 2, 12)   # CE DATE
        sheet.set_column(3, 3, 40)   # DESCRIPTION
        sheet.set_column(4, 4, 8)    # Year
        sheet.set_column(5, 5, 15)   # Balance (prev month)
        sheet.set_column(6, 6, 18)   # System Reversal
        sheet.set_column(7, 7, 18)   # System Accrual
        sheet.set_column(8, 8, 18)   # Manual Reversal
        sheet.set_column(9, 9, 18)   # Manual Re-accrual
        sheet.set_column(10, 10, 18) # Manual Adjustment
        sheet.set_column(11, 11, 15) # Balance (current month)
        sheet.set_column(12, 12, 20) # CE Status
        
        # Write report header
        row = 0
        sheet.write(row, 0, 'ACE SAATCHI AND SAATCHI ADVERTISING INC', formats['title'])
        row += 1
        sheet.write(row, 0, f'ACCRUED REVENUE - {accrual_month_full}', formats['title'])
        row += 1
        sheet.write(row, 0, report_date, formats['title'])
        row += 2
        
        # Write section headers row
        sheet.write(row, 5, f'Balance\n{prev_month_last_day}-{prev_month_abbr}', formats['section_header'])
        sheet.merge_range(row, 6, row, 7, 'REVENUE ACCRUAL - SYSTEM', formats['section_header'])
        sheet.merge_range(row, 8, row, 10, 'MANUAL ADJUSTMENT', formats['section_header'])
        sheet.write(row, 11, f'Balance\n{accrual_month_last_day}-{accrual_month_abbr}', formats['section_header'])
        
        row += 1
        
        # Write column headers
        headers = [
            'CLIENT', 'CE#', 'CE DATE', 'DESCRIPTION', 'Year',
            f'{prev_month_last_day}-{prev_month_abbr}',
            f'{prev_month_abbr} REVERSAL',
            f'{accrual_month_abbr} ACCRUAL',
            f'{prev_month_abbr} REVERSAL',
            f'{accrual_month_abbr} RE-ACCRUAL',
            f'{accrual_month_abbr} ADDL ADJ',
            f'{accrual_month_last_day}-{accrual_month_abbr}',
            'CE STATUS'
        ]
        
        for col, header in enumerate(headers):
            sheet.write(row, col, header, formats['column_header'])
        
        sheet.autofilter(row, 0, row, len(headers) - 1)
        row += 1
        
        # Write data rows
        for partner_name in sorted(grouped_data.keys()):
            ces = grouped_data[partner_name]
            
            for ce_code in sorted(ces.keys()):
                ce_data = ces[ce_code]
                amounts = self._calculate_amounts_by_type(ce_data['lines'], accrual_month)
                
                sheet.write(row, 0, partner_name, formats['normal'])
                sheet.write(row, 1, ce_code, formats['centered'])
                
                if ce_data['ce_date']:
                    sheet.write(row, 2, ce_data['ce_date'], formats['date'])
                else:
                    sheet.write(row, 2, '', formats['centered'])
                
                sheet.write(row, 3, ce_data['description'], formats['normal'])
                
                if ce_data['year']:
                    sheet.write(row, 4, ce_data['year'], formats['centered'])
                else:
                    sheet.write(row, 4, '', formats['centered'])
                
                sheet.write(row, 5, 0, formats['currency'])
                sheet.write(row, 6, amounts['system_reversal'], formats['currency_negative'])
                sheet.write(row, 7, amounts['system_accrual'], formats['currency_negative'])
                sheet.write(row, 8, amounts['manual_reversal'], formats['currency_negative'])
                sheet.write(row, 9, amounts['manual_reaccrual'], formats['currency_negative'])
                sheet.write(row, 10, amounts['manual_adjustment'], formats['currency_negative'])
                
                excel_row = row + 1
                sheet.write_formula(row, 11, f'=F{excel_row}+G{excel_row}+H{excel_row}+I{excel_row}+J{excel_row}+K{excel_row}', formats['currency'])
                
                sheet.write(row, 12, ce_data['ce_status'], formats['centered'])
                
                row += 1
        
        # Generate additional sheets
        self._generate_accrual_breakdown_sheet(workbook, formats, all_lines, accrual_month, accrued_account_id)
        self._generate_gl_sheet(workbook, formats, all_lines, accrual_month, accrued_account_id)
    
    def _generate_accrual_breakdown_sheet(self, workbook, formats, lines, accrual_month, accrued_account_id):
        """Generate the breakdown sheet for accrual entries"""
        accrual_month_end = (accrual_month + relativedelta(months=1)) - relativedelta(days=1)
        
        accrual_lines = lines.filtered(lambda l: 
            l.x_type_of_entry in ['accrued_system', 'accrued_manual'] and 
            l.account_id.id != accrued_account_id and
            l.date and
            accrual_month <= l.date <= accrual_month_end
        )
        
        if not accrual_lines:
            return
        
        sheet_name = accrual_month.strftime('%B %Y Accruals')
        sheet = workbook.add_worksheet(sheet_name)
        
        sheet.set_column(0, 0, 12); sheet.set_column(1, 1, 15); sheet.set_column(2, 2, 20)
        sheet.set_column(3, 3, 25); sheet.set_column(4, 4, 30); sheet.set_column(5, 5, 15)
        sheet.set_column(6, 6, 12); sheet.set_column(7, 7, 35); sheet.set_column(8, 8, 20)
        sheet.set_column(9, 9, 15); sheet.set_column(10, 10, 15); sheet.set_column(11, 11, 15)
        sheet.set_column(12, 12, 30)
        
        row = 0
        headers = ['Date', 'Entry Type', 'Journal Entry', 'Account', 'Client Name', 'CE Code', 'CE Date', 'Label', 'Reference', 'C.E. Status', 'Debit', 'Credit', 'Remarks']
        
        for col, header in enumerate(headers):
            sheet.write(row, col, header, formats['column_header'])
        
        sheet.autofilter(row, 0, row, len(headers) - 1)
        row += 1
        
        sorted_lines = accrual_lines.sorted(key=lambda l: (l.date or datetime.date.min, l.partner_id.name or ''))
        
        for line in sorted_lines:
            if line.date:
                sheet.write(row, 0, line.date, formats['date'])
            else:
                sheet.write(row, 0, '', formats['centered'])
            
            entry_type_display = 'Accrued - System' if line.x_type_of_entry == 'accrued_system' else 'Accrued - Manual'
            sheet.write(row, 1, entry_type_display, formats['normal'])
            sheet.write(row, 2, line.move_id.name if line.move_id else '', formats['normal'])
            sheet.write(row, 3, line.account_id.display_name if line.account_id else '', formats['normal'])
            sheet.write(row, 4, line.partner_id.name if line.partner_id else '', formats['normal'])
            sheet.write(row, 5, line.x_ce_code or '', formats['centered'])
            
            if line.x_ce_date:
                sheet.write(row, 6, line.x_ce_date, formats['date'])
            else:
                sheet.write(row, 6, '', formats['centered'])
            
            sheet.write(row, 7, line.name or '', formats['normal'])
            sheet.write(row, 8, line.x_reference or '', formats['normal'])
            
            var = line._fields['x_ce_status'].selection(line)
            ce_status = dict(var).get(line.x_ce_status)
            sheet.write(row, 9, ce_status, formats['centered'])
            
            sheet.write(row, 10, line.debit or 0, formats['currency'])
            sheet.write(row, 11, line.credit or 0, formats['currency'])
            sheet.write(row, 12, line.x_studio_remarks or '', formats['normal'])
            
            row += 1
        
        return True
            
    def _generate_gl_sheet(self, workbook, formats, lines, accrual_month, accrued_account_id):
        """Generate the GL sheet for all accrued revenue account entries"""
        accrual_month_end = (accrual_month + relativedelta(months=1)) - relativedelta(days=1)
        
        gl_lines = lines.filtered(lambda l: 
            l.account_id.id == accrued_account_id and
            l.date and
            accrual_month <= l.date <= accrual_month_end
        )
        
        if not gl_lines:
            return
        
        month_name = accrual_month.strftime('%B')
        sheet_name = f'GL_{month_name}'
        sheet = workbook.add_worksheet(sheet_name)
        
        base_font = {'font_name': 'Calibri', 'font_size': 10}
        currency_bold_format = workbook.add_format({**base_font, 'bold': True, 'num_format': '#,##0.00;-#,##0.00;"-"', 'align': 'right', 'valign': 'vcenter', 'border': 1})
        currency_negative_bold_format = workbook.add_format({**base_font, 'bold': True, 'num_format': '#,##0.00;(#,##0.00);"-"', 'align': 'right', 'valign': 'vcenter', 'border': 1})
        
        sheet.set_column(0, 0, 12); sheet.set_column(1, 1, 15); sheet.set_column(2, 2, 20); sheet.set_column(3, 3, 25)
        sheet.set_column(4, 4, 30); sheet.set_column(5, 5, 15); sheet.set_column(6, 6, 12); sheet.set_column(7, 7, 35)
        sheet.set_column(8, 8, 20); sheet.set_column(9, 9, 15); sheet.set_column(10, 10, 15); sheet.set_column(11, 11, 15)
        sheet.set_column(12, 12, 15); sheet.set_column(13, 13, 30)
        
        row = 0
        headers = ['Date', 'Entry Type', 'Journal Entry', 'Account', 'Client Name', 'CE Code', 'CE Date', 'Label', 'Reference', 'C.E. Status', 'Debit', 'Credit', 'DR Less CR', 'Remarks']
        
        for col, header in enumerate(headers):
            sheet.write(row, col, header, formats['column_header'])
        
        sheet.autofilter(row, 0, row, len(headers) - 1)
        row += 1
        data_start_row = row
        
        sorted_lines = gl_lines.sorted(key=lambda l: (l.date or datetime.date.min, l.partner_id.name or ''))
        
        for line in sorted_lines:
            if line.date:
                sheet.write(row, 0, line.date, formats['date'])
            else:
                sheet.write(row, 0, '', formats['centered'])
            
            entry_type_map = {
                'accrued_system': 'Accrued - System',
                'accrued_manual': 'Accrued - Manual',
                'reversal_system': 'Reversal - System',
                'reversal_manual': 'Reversal - Manual',
                'adjustment_system': 'Adjustment - System',
                'adjustment_manual': 'Adjustment - Manual'
            }
            sheet.write(row, 1, entry_type_map.get(line.x_type_of_entry, ''), formats['normal'])
            sheet.write(row, 2, line.move_id.name if line.move_id else '', formats['normal'])
            sheet.write(row, 3, line.account_id.display_name if line.account_id else '', formats['normal'])
            sheet.write(row, 4, line.partner_id.name if line.partner_id else '', formats['normal'])
            sheet.write(row, 5, line.x_ce_code or '', formats['centered'])
            
            if line.x_ce_date:
                sheet.write(row, 6, line.x_ce_date, formats['date'])
            else:
                sheet.write(row, 6, '', formats['centered'])
            
            sheet.write(row, 7, line.name or '', formats['normal'])
            sheet.write(row, 8, line.x_reference or '', formats['normal'])
            
            var = line._fields['x_ce_status'].selection(line)
            ce_status = dict(var).get(line.x_ce_status)
            sheet.write(row, 9, ce_status, formats['centered'])
            
            sheet.write(row, 10, line.debit or 0, formats['currency'])
            sheet.write(row, 11, line.credit or 0, formats['currency'])
            
            excel_row = row + 1
            sheet.write_formula(row, 12, f'=K{excel_row}-L{excel_row}', formats['currency_negative'])
            
            sheet.write(row, 13, line.x_studio_remarks or '', formats['normal'])
            
            row += 1
        
        total_row = row
        
        for col in range(0, 9):
            sheet.write(total_row, col, '', formats['section_header_no_border'])
        
        bold_with_border = workbook.add_format({'font_name': 'Calibri', 'font_size': 10, 'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1})
        sheet.write(total_row, 9, 'TOTAL', bold_with_border)
        
        sheet.write_formula(total_row, 10, f'=SUM(K{data_start_row + 1}:K{total_row})', currency_bold_format)
        sheet.write_formula(total_row, 11, f'=SUM(L{data_start_row + 1}:L{total_row})', currency_bold_format)
        sheet.write_formula(total_row, 12, f'=SUM(M{data_start_row + 1}:M{total_row})', currency_negative_bold_format)
        sheet.write(total_row, 13, '', formats['section_header_no_border'])
        
        return True