/** @odoo-module */
import { ListController } from "@web/views/list/list_controller";
import { registry } from '@web/core/registry';
import { listView } from '@web/views/list/list_view';

export class UnfoldAllListController extends ListController {
    setup() {
        super.setup();
    }
    
    async onUnfoldAllClick() {
        const groupHeaders = Array.from(document.querySelectorAll('.o_group_header.o_group_has_content'));
        const foldedHeaders = groupHeaders.filter(header => header.querySelector('.fa-caret-right'));
        
        // Click all at once without waiting
        foldedHeaders.forEach(header => header.click());
    }
    
    async onFoldAllClick() {
        const groupHeaders = Array.from(document.querySelectorAll('.o_group_header.o_group_has_content'));
        const unfoldedHeaders = groupHeaders.filter(header => header.querySelector('.fa-caret-down'));
        
        // Click all at once without waiting
        unfoldedHeaders.forEach(header => header.click());
    }
}

// Link controller to the template with buttons
UnfoldAllListController.template = "saatchi.accrued_revenue_journal_items.ListView.Buttons";

export const customUnfoldAllListController = {
    ...listView,
    Controller: UnfoldAllListController,
};

// Register the custom list controller
registry.category("views").add("unfold_all_list", customUnfoldAllListController);