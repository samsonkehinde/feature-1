odoo.define('drugstoc_mobile.pos_pay_central', function (require) {
"use strict";

var core    = require('web.core');
var _t      = core._t;
const Swal = require('sweetalert2')

let timerInterval
Swal.fire({
  title: 'Payment was successful!',
  html: 'Will close in <strong></strong> seconds.',
  timer: 5000,
  onBeforeOpen: () => {
    Swal.showLoading()
    timerInterval = setInterval(() => {
      Swal.getContent().querySelector('strong').textContent = Math.floor(Swal.getTimerLeft()/1000)
    }, 1000)
  },
  onClose: () => {
    clearInterval(timerInterval)
  }
}).then((result) => {

   console.log('I was closed by the timer')
   window.close()
})
//var PopupWidget = require('point_of_sale.popups');
//pos_model.PosModel = pos_model.PosModel.extend({

//});
