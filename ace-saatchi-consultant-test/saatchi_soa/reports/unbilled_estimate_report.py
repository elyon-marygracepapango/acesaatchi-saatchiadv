from odoo import models
import datetime
from xlsxwriter.workbook import Workbook
from odoo.exceptions import ValidationError, UserError
import pytz
import logging

_logger = logging.getLogger(__name__)

class UnbilledEstimateXLSX(models.AbstractModel):
    _name = 'report.unbilled_estimate_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Unbilled Estimate XLSX Report'

    def _define_formats(self, workbook):
        """Define and return format objects."""
        base_font = {'font_name': 'Arial', 'font_size': 9}
        
        # Header formats
        company_format = workbook.add_format({
            'font_name': 'Arial',
            'font_size': 9,
            'align': 'left',
            'valign': 'top'
        })
        
        title_format = workbook.add_format({
            'font_name': 'Arial',
            'font_size': 11,
            'bold': True,
            'align': 'center',
            'valign': 'vcenter'
        })
        
        date_user_format = workbook.add_format({
            'font_name': 'Arial',
            'font_size': 8,
            'align': 'right',
            'valign': 'top'
        })
        
        # Main header format (Approved Estimated, Invoiced to date, Variance)
        main_header_approved = workbook.add_format({
            **base_font,
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#366092',  # Dark blue
            'font_color': 'white',
            'border': 1,
            'border_color': '#000000'
        })
        
        main_header_invoiced = workbook.add_format({
            **base_font,
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#F79646',  # Orange
            'font_color': 'white',
            'border': 1,
            'border_color': '#000000'
        })
        
        main_header_variance = workbook.add_format({
            **base_font,
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#FFFF00',  # Yellow
            'font_color': 'black',
            'border': 1,
            'border_color': '#000000'
        })
        
        main_header_remarks = workbook.add_format({
            **base_font,
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#375623',  # Dark green
            'font_color': 'white',
            'border': 1,
            'border_color': '#000000'
        })
        
        # CE Status header format (same green as Remarks)
        main_header_ce_status = workbook.add_format({
            **base_font,
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#375623',  # Dark green
            'font_color': 'white',
            'border': 1,
            'border_color': '#000000'
        })
        
        # Sub-header format (Billing/Revenue) - with same background colors
        sub_header_approved = workbook.add_format({
            **base_font,
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#366092',
            'font_color': 'white',
            'border': 1,
            'border_color': '#000000'
        })
        
        sub_header_invoiced = workbook.add_format({
            **base_font,
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#F79646',
            'font_color': 'white',
            'border': 1,
            'border_color': '#000000'
        })
        
        sub_header_variance = workbook.add_format({
            **base_font,
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#FFFF00',
            'font_color': 'black',
            'border': 1,
            'border_color': '#000000'
        })
        
        # Job column header - NO background color
        job_header_format = workbook.add_format({
            **base_font,
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'border_color': '#000000'
        })
        
        # Data row formats - NO BORDERS
        partner_format = workbook.add_format({
            **base_font,
            'bold': True,
            'align': 'left',
            'valign': 'vcenter'
        })
        
        ce_format = workbook.add_format({
            **base_font,
            'align': 'left',
            'valign': 'vcenter',
            'indent': 1
        })
        
        currency_format = workbook.add_format({
            **base_font,
            'num_format': '#,##0.00',
            'align': 'right',
            'valign': 'vcenter'
        })
        
        # Subtotal format - WITH TOP BORDER ONLY (on numeric columns only)
        currency_subtotal_format = workbook.add_format({
            **base_font,
            'bold': True,
            'num_format': '#,##0.00',
            'align': 'right',
            'valign': 'vcenter',
            'top': 1,
            'top_color': '#000000'
        })
        
        # Subtotal dash format - for empty values in subtotal row with top border
        subtotal_dash_format = workbook.add_format({
            **base_font,
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'top': 1,
            'top_color': '#000000'
        })
        
        text_format = workbook.add_format({
            **base_font,
            'align': 'left',
            'valign': 'vcenter'
        })
        
        # CE Status format - centered and bold
        ce_status_format = workbook.add_format({
            **base_font,
            'bold': True,
            'align': 'center',
            'valign': 'vcenter'
        })
        
        dash_format = workbook.add_format({
            **base_font,
            'align': 'center',
            'valign': 'vcenter'
        })
        
        empty_cell_format = workbook.add_format({})
        
        # Subtotal empty format - NO border for Job and Remarks columns
        subtotal_empty_format = workbook.add_format({})
        
        return {
            'company': company_format,
            'title': title_format,
            'date_user': date_user_format,
            'main_header_approved': main_header_approved,
            'main_header_invoiced': main_header_invoiced,
            'main_header_variance': main_header_variance,
            'main_header_remarks': main_header_remarks,
            'main_header_ce_status': main_header_ce_status,
            'sub_header_approved': sub_header_approved,
            'sub_header_invoiced': sub_header_invoiced,
            'sub_header_variance': sub_header_variance,
            'job_header': job_header_format,
            'partner': partner_format,
            'ce': ce_format,
            'currency': currency_format,
            'currency_subtotal': currency_subtotal_format,
            'text': text_format,
            'ce_status': ce_status_format,
            'dash': dash_format,
            'empty': empty_cell_format,
            'subtotal_empty': subtotal_empty_format,
            'subtotal_dash': subtotal_dash_format
        }

    def generate_xlsx_report(self, workbook, data, lines):
        """Main report generation method."""
        formats = self._define_formats(workbook)
        
        # Get current user and datetime in GMT+8
        current_user = self.env.user.name
        user_tz = pytz.timezone('Asia/Manila')  # GMT+8
        now = datetime.datetime.now(pytz.UTC).astimezone(user_tz)
        report_datetime = now.strftime('%m/%d/%Y - %I:%M %p')
        sheet_date = now.strftime('%m/%d/%Y')
        
        # Create sheet
        sheet = workbook.add_worksheet('Unbilled Estimate Report')
        
        # Set column widths to match the reference
        sheet.set_column(0, 0, 45)   # Job column
        sheet.set_column(1, 1, 13)   # Billing (Approved)
        sheet.set_column(2, 2, 13)   # Revenue (Approved)
        sheet.set_column(3, 3, 13)   # Billing (Invoiced)
        sheet.set_column(4, 4, 13)   # Revenue (Invoiced)
        sheet.set_column(5, 5, 13)   # Billing (Variance)
        sheet.set_column(6, 6, 13)   # Revenue (Variance)
        sheet.set_column(7, 7, 20)   # CE Status (widened)
        sheet.set_column(8, 8, 20)   # Remarks
        
        # Set row heights
        sheet.set_row(0, 15)  # Company row
        sheet.set_row(2, 15)  # Date/user row
        sheet.set_row(4, 20)  # Main header row
        sheet.set_row(5, 20)  # Sub header row
        
        # Write header - Company name (top left)
        sheet.write(0, 0, self.env.company.name, formats['company'])
        
        # Write title (centered, row 2, merged across all columns)
        sheet.merge_range(1, 0, 1, 8, 'Unbilled Estimate Report', formats['title'])
        
        # Write date and user (top right)
        sheet.write(2, 8, f'{report_datetime} - {current_user}', formats['date_user'])
        
        # Starting row for table headers
        header_row = 4
        
        # Write main column headers (Row 1)
        # Job column spans 2 rows
        sheet.merge_range(header_row, 0, header_row + 1, 0, 'Job', formats['job_header'])
        
        # Approved Estimated (merged across Billing and Revenue)
        sheet.merge_range(header_row, 1, header_row, 2, 'Approved Estimated', formats['main_header_approved'])
        
        # Invoiced to date (merged across Billing and Revenue)
        sheet.merge_range(header_row, 3, header_row, 4, 'Invoiced to date', formats['main_header_invoiced'])
        
        # Variance (merged across Billing and Revenue)
        sheet.merge_range(header_row, 5, header_row, 6, 'Variance', formats['main_header_variance'])
        
        # CE Status spans 2 rows
        sheet.merge_range(header_row, 7, header_row + 1, 7, 'CE Status', formats['main_header_ce_status'])
        
        # Remarks spans 2 rows
        sheet.merge_range(header_row, 8, header_row + 1, 8, 'Remarks', formats['main_header_remarks'])
        
        # Write sub-headers (Row 2 - Billing/Revenue)
        sub_header_row = header_row + 1
        sheet.write(sub_header_row, 1, 'Billing', formats['sub_header_approved'])
        sheet.write(sub_header_row, 2, 'Revenue', formats['sub_header_approved'])
        sheet.write(sub_header_row, 3, 'Billing', formats['sub_header_invoiced'])
        sheet.write(sub_header_row, 4, 'Revenue', formats['sub_header_invoiced'])
        sheet.write(sub_header_row, 5, 'Billing', formats['sub_header_variance'])
        sheet.write(sub_header_row, 6, 'Revenue', formats['sub_header_variance'])
        
        # Add autofilter to header row
        sheet.autofilter(sub_header_row, 0, sub_header_row, 8)

        # Protect sheet with password
        sheet.protect('1234', {
            'autofilter': True,  # Allow filtering
            'sort': True,        # Allow sorting
        })
        
        current_row = sub_header_row + 1
        
        # Group sale orders by partner (filter only with CE code and sale status)
        partners_dict = {}
        for order in lines:
            # Filter: only orders with CE code and in 'sale' state
            if not order.x_ce_code or order.state != 'sale':
                continue
                
            partner_name = order.partner_id.name or 'Unknown Partner'
            if partner_name not in partners_dict:
                partners_dict[partner_name] = []
            partners_dict[partner_name].append(order)
        
        # Sort partners alphabetically
        sorted_partners = sorted(partners_dict.keys())
        
        # Generate data rows
        for partner_name in sorted_partners:
            orders = partners_dict[partner_name]
            
            # Sort orders by CE code within partner
            orders_sorted = sorted(orders, key=lambda x: x.x_ce_code or '')
            
            # Write partner row
            sheet.write(current_row, 0, partner_name, formats['partner'])
            for col in range(1, 9):
                sheet.write(current_row, col, '', formats['empty'])
            sheet.set_row(current_row, 18)
            current_row += 1
            
            # Initialize subtotals for this partner
            subtotal = {
                'approved_billing': 0,
                'approved_revenue': 0,
                'invoiced_billing': 0,
                'invoiced_revenue': 0,
                'variance_billing': 0,
                'variance_revenue': 0
            }
            
            # Write CE/SO rows
            for order in orders_sorted:
                # CE# + Job Description
                ce_text = f"{order.x_ce_code or ''} - {order.x_job_description or ''}".strip(' -')
                sheet.write(current_row, 0, ce_text, formats['ce'])
                
                # Approved Estimate
                self._write_value(sheet, current_row, 1, order.x_ce_approved_estimate_billing, formats)
                self._write_value(sheet, current_row, 2, order.x_ce_approved_estimate_revenue, formats)
                
                # Invoiced to date
                self._write_value(sheet, current_row, 3, order.x_ce_invoiced_billing, formats)
                self._write_value(sheet, current_row, 4, order.x_ce_invoiced_revenue, formats)
                
                # Variance
                self._write_value(sheet, current_row, 5, order.x_ce_variance_billing, formats)
                self._write_value(sheet, current_row, 6, order.x_ce_variance_revenue, formats)
                
                # CE Status - centered, bold, and uppercase (get label, not technical value)
                if order.x_ce_status:
                    selection_list = order._fields['x_ce_status'].selection
                    ce_status = dict(selection_list).get(order.x_ce_status)
                    if ce_status:
                        sheet.write(current_row, 7, ce_status.upper(), formats['ce_status'])
                    else:
                        sheet.write(current_row, 7, '', formats['empty'])
                else:
                    sheet.write(current_row, 7, '', formats['empty'])
                
                # Remarks
                remarks = order.x_remarks or ''
                if remarks:
                    sheet.write(current_row, 8, remarks, formats['text'])
                else:
                    sheet.write(current_row, 8, '', formats['empty'])
                
                # Add to subtotals
                subtotal['approved_billing'] += order.x_ce_approved_estimate_billing or 0
                subtotal['approved_revenue'] += order.x_ce_approved_estimate_revenue or 0
                subtotal['invoiced_billing'] += order.x_ce_invoiced_billing or 0
                subtotal['invoiced_revenue'] += order.x_ce_invoiced_revenue or 0
                subtotal['variance_billing'] += order.x_ce_variance_billing or 0
                subtotal['variance_revenue'] += order.x_ce_variance_revenue or 0
                
                sheet.set_row(current_row, 18)
                current_row += 1
            
            # Write subtotal row for partner - ALL numeric columns get top border
            sheet.write(current_row, 0, '', formats['empty'])
            
            # All numeric columns (1-6) get top border regardless of value
            if subtotal['approved_billing']:
                sheet.write(current_row, 1, subtotal['approved_billing'], formats['currency_subtotal'])
            else:
                sheet.write(current_row, 1, '-', formats['subtotal_dash'])
                
            if subtotal['approved_revenue']:
                sheet.write(current_row, 2, subtotal['approved_revenue'], formats['currency_subtotal'])
            else:
                sheet.write(current_row, 2, '-', formats['subtotal_dash'])
                
            if subtotal['invoiced_billing']:
                sheet.write(current_row, 3, subtotal['invoiced_billing'], formats['currency_subtotal'])
            else:
                sheet.write(current_row, 3, '-', formats['subtotal_dash'])
                
            if subtotal['invoiced_revenue']:
                sheet.write(current_row, 4, subtotal['invoiced_revenue'], formats['currency_subtotal'])
            else:
                sheet.write(current_row, 4, '-', formats['subtotal_dash'])
                
            if subtotal['variance_billing']:
                sheet.write(current_row, 5, subtotal['variance_billing'], formats['currency_subtotal'])
            else:
                sheet.write(current_row, 5, '-', formats['subtotal_dash'])
                
            if subtotal['variance_revenue']:
                sheet.write(current_row, 6, subtotal['variance_revenue'], formats['currency_subtotal'])
            else:
                sheet.write(current_row, 6, '-', formats['subtotal_dash'])
                
            # CE Status and Remarks columns - no border
            sheet.write(current_row, 7, '', formats['empty'])
            sheet.write(current_row, 8, '', formats['empty'])
            
            sheet.set_row(current_row, 18)
            current_row += 1
        
        return True
    
    def _write_value(self, sheet, row, col, value, formats):
        """Helper method to write value or dash if empty/zero."""
        if value:
            sheet.write(row, col, value, formats['currency'])
        else:
            sheet.write(row, col, '-', formats['dash'])