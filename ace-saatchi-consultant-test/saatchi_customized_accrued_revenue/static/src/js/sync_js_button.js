/** @odoo-module */
import { ListController } from "@web/views/list/list_controller";
import { registry } from '@web/core/registry';
import { listView } from '@web/views/list/list_view';
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

export class SaatchiAccruedRevenueListController extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.dialogService = useService("dialog");
        this.notification = useService("notification");
        this.actionService = useService("action"); // <-- Added action service
    }

    async OnTestClick() {
        // Show Odoo confirmation dialog
        this.dialogService.add(ConfirmationDialog, {
            title: "Confirm Action",
            body: "Are you sure you want to sync new records for accrual? This will process all eligible sale orders.",
            confirm: async () => {
                const result = await this.orm.call(
                    'saatchi.accrued_revenue',
                    'sync_new_records_for_accrual',
                    [[]]  // Pass empty list of IDs, as first argument
                );

                // If the result is an action (like wizard), open it
                if (result && result.type) {
                    await this.actionService.doAction(result); // <-- Use actionService here
                } 
                // If result is a number, show notification
                else if (result > 0) {
                    this.notification.add(
                        `Successfully created ${result} new draft for accrual.`,
                        { type: "success", title: "Success!" }
                    );
                } 
                // No records created
                else {
                    this.notification.add(
                        "No new records were created for accrual.",
                        { type: "info", title: "Info" }
                    );
                }

                // Refresh the view
                await this.model.root.load();
                this.render(true);
            },
            cancel: () => {
                // User cancelled, do nothing
            }
        });
    }
}

// Link controller to the template with buttons
SaatchiAccruedRevenueListController.template = "saatchi.accrued_revenue.ListView.Buttons";

export const customSaatchiAccruedRevenueListController = {
    ...listView,
    Controller: SaatchiAccruedRevenueListController,
};

// Register the custom list controller
registry.category("views").add("button_in_list", customSaatchiAccruedRevenueListController);
