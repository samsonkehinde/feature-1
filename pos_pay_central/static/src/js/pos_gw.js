odoo.define('pos_pay_central.pos_pay_central', function (require) {
"use strict";

var core    = require('web.core');
var rpc    = require('web.rpc');
var screens = require('point_of_sale.screens');
var gui     = require('point_of_sale.gui');
var pos_model = require('point_of_sale.models');
var _t      = core._t;

var ScreenWidget = screens.ScreenWidget;
var PaymentScreenWidget = screens.PaymentScreenWidget;
var PopupWidget = require('point_of_sale.popups');

pos_model.load_fields("account.journal", "pos_pg_config_id");

pos_model.PosModel = pos_model.PosModel.extend({
// Get Journals with Payment Method equal to any of the defined electronic payment gateways.
    getOnlinePaymentJournals: function () {
        var self = this;
        var online_payment_journals = [];

        $.each(this.journals, function (idx, journal) {
            if (journal.pos_pg_config_id) {
                online_payment_journals.push({label:self.getCashRegisterByJournalID(journal.id).journal_id[1], item:journal.id});
            }
        });

        return online_payment_journals;
    },

    getCashRegisterByJournalID: function (journal_id) {// Get the CashRegister with a journal_id matching the supplied.
        var cashregister_return;

        $.each(this.cashregisters, function (idx, cashregister) {
            if (cashregister.journal_id[0] === journal_id) {
                cashregister_return = cashregister;
            }
        });

        return cashregister_return;
    }
});

var _paylineproto = pos_model.Paymentline.prototype;

pos_model.Paymentline = pos_model.Paymentline.extend({
    init_from_JSON: function (json) {//Init the Payment Line from JSON
        _paylineproto.init_from_JSON.apply(this, arguments);// Reference to the original version of this method

        // Add our Payment Gateway Extras to the JSON Initialized Object.
        this.paid = json.paid;
        this.pos_payment_method = json.pos_payment_method;
        this.pos_card_number = json.pos_card_number;
        this.pos_card_owner_name = json.pos_card_owner_name;
        this.pos_ref_no = json.pos_ref_no;
        this.pos_invoice_no = json.pos_invoice_no;
        this.pos_sales_person = json.pos_sales_person;
    },
    export_as_JSON: function () {// Export the Payment Line to JSON.
        return _.extend(_paylineproto.export_as_JSON.apply(this, arguments), {
            paid: this.paid,
            pos_payment_method: this.pos_payment_method,
            pos_card_number: this.pos_card_number,
            pos_card_owner_name: this.pos_card_owner_name,
            pos_ref_no: this.pos_ref_no,
            pos_invoice_no: this.pos_invoice_no,
            pos_sales_person: this.pos_sales_person,
        });
    }
});

var PaymentTransactionPopupWidget = PopupWidget.extend({
    template: 'PaymentPopupWidget',
    show: function (options) {
        this.txn_ref = ""; // Hide the OTP Controls
        this.opts = options; // Save the initial passed options.
        this.opts.message = '<strong>PAY:  ' + options.cash_reg.currency_id[1] + options.caller_ref.pos.get_order().get_due() + "</strong>";
        //console.log(this.opts);
        var self = this;
        this._super(options);
        self.$el.find('div#status').html(options.message);
    },events: {
        'click .button.cancel':  'click_cancel',
        'click .button.confirm': 'click_pay'
    },
    click_pay: function(){
        var self = this;
        // 1 - Validate all Fields
        if(self.txn_ref){ // We are Processing OTP
           if(self.validate_otp_input()){
                this.process_txn("send_otp",[{'ref': this.txn_ref,'otp': self.$el.find('#otp').val(),"journal_id": self.opts.cash_reg.journal_id[0]}]);
            }
        }else{
            if(self.validate_payment_input()){
                // Process the Card Expiry
                var ex = self.$el.find('#card_expiry').val();
                var expiry = ex.indexOf("/") === -1 ? ex.split("\\") : ex.split("/");
                var proc_data = [{'journal_id': self.opts.cash_reg.journal_id[0],'amount': (self.opts.caller_ref.pos.get_order().get_due() * 100), 'cvv': self.$el.find('#card_cvv').val(),'pan': self.$el.find('#card_pan').val(),'expiry_month': expiry[0],"expiry_year": expiry[1],'email': self.$el.find('#card_email').val(),'pin': self.$el.find('#card_pin').val()}];
                this.process_txn("process_payment",proc_data);
            }
        }
    },
    process_txn: function(pMethod,pData){
        var self = this;
        //console.log(self.txn_ref);
        // 2 - Process payment through the Selected Payment Gateway
        $('div#status').html('Processing...');
        rpc.query({
            model: 'pos_pay_central.payment_processor',
            method: pMethod,
            args: pData
        }, {
            timeout: 10000,
        })
        .then(function (resp) {
            //console.log(resp);
            if(resp.status === "Setup Incomplete" || resp.status === "Configuration Error") {
                // Display the error temporarily for 5 seconds
                self.display_msg(5000,resp,self.$el.find('div#status'),self.opts.message);
                return;
            }
            else if(resp.status === "Approved") {
                // 3 - If Payment was successfully, Update Status & Autoclose the Popup after 2 seconds.
                self.$el.find('div#status').html("Payment Succesful");

                // Call success callback
                self.success_cb(resp);

                // Autoclose this gui after 3 seconds
                setTimeout(function(){
                    self.gui.close_popup();
                    self.toggle_controls("");
                }, 3000);

            }else if(resp.status === "send_otp") {
                  self.$el.find('div#status').html("ENTER OTP");
                  self.toggle_controls(resp.ref);// Hide other Inputs and Un-Hide the OTP Input, hide "Pay" Button and Un-Hide Send OTP button.

            }else if(resp.status === "send_pin"){
                self.display_msg(5000,"Incorrect PIN!",self.$el.find('div#status'),self.opts.message);
            }else{
                // Display Payment Error Message
                self.display_msg(5000,resp.status,self.$el.find('div#status'),self.opts.message);
                // Autoclose this gui after 3 seconds
/*                setTimeout(function(){
                    self.gui.close_popup();
                    self.toggle_controls("");
                }, 3000);*/
            }
        }).fail(function (type, error) {
            //console.log(type);
            // Display Payment Error Message
            self.display_msg(5000,type.message,self.$el.find('div#status'),self.opts.message);
        })
    },
        toggle_controls: function(txn_ref){
            this.txn_ref = txn_ref;
            if(this.txn_ref){
                // Hide Card Inputs/Buttons and Show OTP Input/Button
                this.$el.find("#payment_controls").hide();
                this.$el.find("#otp_controls").show();
                this.$el.find(".button.confirm").text('Send OTP');
            }else{
                // Show Card Inputs/Buttons and Hide OTP Input/Button
                this.$el.find("#payment_controls").show();
                this.$el.find("#otp_controls").hide();
                this.$el.find(".button.confirm").text('PAY');
            }
        }
    ,
    click_cancel: function(){
        this.gui.close_popup();
    },
    validate_otp_input: function(){
        //Validate OTP
        if(! /^\d{6,10}$/.test($("#otp").val())){
            $("#otp").focus();
            // Display the error temporarily for 5 seconds
            this.display_msg(1500,"Invalid OTP",this.$el.find('div#status'),"Enter OTP");
            return false;
        }
        return true;
    },
    validate_payment_input: function(){

        //Validate PAN
        if(! /^\d{12,}$/.test($("#card_pan").val())){
            $("#card_pan").focus();
            // Display the error temporarily for 5 seconds
            this.display_msg(1500,"Invalid PAN",this.$el.find('div#status'),this.opts.message);
            return false;
        }

        //Validate Expiry
        if(! /^(\d{1,2}|1[0-2])[\/\\]\d{2}$/.test($("#card_expiry").val())){
            $("#card_expiry").focus();
            // Display the error temporarily for 5 seconds
            this.display_msg(1500,"Invalid Expiry",this.$el.find('div#status'),this.opts.message);
            return false;
        }

        //Validate CVV
        if(! /^\d{3}$/.test($("#card_cvv").val())){
            $("#card_cvv").focus();
            // Display the error temporarily for 5 seconds
            this.display_msg(1500,"Invalid CVV",this.$el.find('div#status'),this.opts.message);
            return false;
        }

        //Validate Email
        if(! /\S+@\S+\.\S+/.test($("#card_email").val())){
            $("#card_email").focus();
            // Display the error temporarily for 5 seconds
            this.display_msg(1500,"Invalid Email",this.$el.find('div#status'),this.opts.message);
            return false;
        }

        // Check PIN Entry
        if(! /\S+/.test($("#card_pin").val())){
            $("#card_pin").focus();
            // Display the error temporarily for 5 seconds
            this.display_msg(1500,"Enter PIN",this.$el.find('div#status'),this.opts.message);
            return false;
        }

        return true;
    },
    display_msg: function(duration, msg,el,old_msg){
        el.html(msg);// Temporarily display the message for 5 seconds
        setTimeout(function(){
            el.html(old_msg);// Then revert to the initial pay message
            return;
        }, duration);
    },
    success_cb: function(res){
        var self = this.opts.caller_ref, cashregister = this.opts.cash_reg, order = self.pos.get_order();

        // Add Payment Line
        order.add_paymentline(self.pos.getCashRegisterByJournalID(cashregister.journal_id[0]));

        // Update Payment Line
        order.selected_paymentline.paid = true
        order.selected_paymentline.pos_card_number = res.card,
        order.selected_paymentline.pos_ref_no = res.ref
        order.selected_paymentline.pos_sales_person = res.sales_person
        order.selected_paymentline.pos_payment_method = res.processor

        // Update UI
        self.order_changes();
        self.reset_input();
        self.render_paymentlines();
        order.trigger('change', order); // needed so that export_to_JSON gets triggered
    }
});

gui.define_popup({name:'payment-transaction', widget: PaymentTransactionPopupWidget});

var RefundTransactionPopupWidget = PopupWidget.extend({
    template: 'RefundTransactionPopupWidget',
    show: function (options) {
        var self = this;
        this._super(options);
        options.transaction.then(function (data) {
            if (data.auto_close) {
                setTimeout(function () {
                    self.gui.close_popup();
                }, 2000);
            } else {
                self.close();
                self.$el.find('.popup').append('<div class="footer"><div class="button cancel">Ok</div></div>');
            }

            self.$el.find('p.body').html(data.message);
        }).progress(function (data) {
            self.$el.find('p.body').html(data.message);
        });
    }
});

gui.define_popup({name:'refund-transaction', widget: RefundTransactionPopupWidget});

// On Payment screen, allow electronic payments
PaymentScreenWidget.include({

    // Make sure there is only one paymentline waiting to be Completed
    // Note: paymentline maps to a cashregister, cashregister maps to a journal
    click_paymentmethods: function (id) {
        var self = this;
        var i;
        var order = this.pos.get_order();
        var cashregister = null;

        // Get the CashRegister with the received journal_id from the list of POS Registered CashRegisters.
        for (i = 0; i < this.pos.cashregisters.length; i++) {
            if (this.pos.cashregisters[i].journal_id[0] === id){// CashRegisters relationship with Journal_ID is a 1-to-Many
                cashregister = this.pos.cashregisters[i];
                break;
            }
        }

        // If the matching cashregister's journal is electronic payment enabled
        if(this.pos.get_order().get_due()){// We only process payments above 0 NGN
            if (cashregister.journal.pos_pg_config_id) {
                // Display the Payment UI
                this.gui.show_popup('payment-transaction', {
                    caller_ref: this,
                    cash_reg: cashregister
                });
                //console.log(this.pos.get_order().get_due());
            }else{
                this._super(id);
            }
        }
    },

    init: function(parent, options) {
       var self = this;
       this._super(parent, options);
        //Overide methods
       this.keyboard_keydown_handler = function(event){

           if (event.keyCode === 8 || event.keyCode === 46) { // Backspace and Delete
              event.preventDefault();
              self.keyboard_handler(event);
           }
       };

       this.keyboard_handler = function(event){
           var key = '';

          if (event.type === "keypress") {
               if (event.keyCode === 13) { // Enter
                   self.validate_order();
               } else if ( event.keyCode === 190 || // Dot
                           event.keyCode === 110 ||  // Decimal point (numpad)
                           event.keyCode === 188 ||  // Comma
                           event.keyCode === 46 ) {  // Numpad dot
                   key = self.decimal_point;
               } else if (event.keyCode >= 48 && event.keyCode <= 57) { // Numbers
                   key = '' + (event.keyCode - 48);
               } else if (event.keyCode === 45) { // Minus
                   key = '-';
               } else if (event.keyCode === 43) { // Plus
                   key = '+';
               }else{
                return ;
               }
           } else { // keyup/keydown
               if (event.keyCode === 46) { // Delete
                   key = 'CLEAR';
               } else if (event.keyCode === 8) { // Backspace
                   key = 'BACKSPACE';
               }
           }

           self.payment_input(key);
          // event.preventDefault();
       };
       //End method override
   },

    do_reversal: function (line) {
        var def = new $.Deferred();
        var self = this;

        // show the transaction popup.
        // the transaction deferred is used to update transaction status
        self.gui.show_popup('refund-transaction', {
            transaction: def
        });

        def.notify({
            message: 'Processing...'
        });

        rpc.query(
        {
            model: 'pos_pay_central.payment_processor',
            method: 'process_refund',
            args: [{"ref": line.pos_ref_no,"journal_id": line.cashregister.journal_id[0],"amount": line.amount*100}]
        }, {
            timeout: 10000   // Request timesout after 10secs
        }).then(function (resp) {
            console.log(resp);
            if (resp.status === "internal error" || resp.status === "timeout") {
                def.resolve({
                    message: "Internal Error."
                });
                return;
            }
            else if (resp.status === "Approved") {
                //Remove Payment Line
                self.pos.get_order().remove_paymentline(line);
                self.reset_input();
                self.render_paymentlines();

                //Show complete and autoclose popup
                def.resolve({
                    message: "Reversal Complete!",
                    auto_close: true
                });
            }
        }).fail(function (type, error) {
            def.resolve({
                message: _t("Reversal Failed.")
            });
        });
    },

    click_delete_paymentline: function (cid) {
        var lines = this.pos.get_order().get_paymentlines();

        for (var i = 0; i < lines.length; i++) {
            if (lines[i].cid === cid && lines[i].pos_payment_method) {
                this.do_reversal(lines[i]);
                return;
            }
        }

        this._super(cid);
    }
});

});
