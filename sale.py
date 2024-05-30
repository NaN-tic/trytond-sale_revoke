# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
import logging
from datetime import timedelta
from trytond.pool import Pool, PoolMeta
from trytond.model import ModelView
from trytond.model import fields
from trytond.transaction import Transaction
from trytond.exceptions import UserError
from trytond.i18n import gettext
from trytond.pyson import Bool, Eval
from trytond.wizard import (
    Button, StateAction, StateTransition, StateView, Wizard)

logger = logging.getLogger(__name__)

class Cron(metaclass=PoolMeta):
    __name__ = 'ir.cron'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.method.selection += [
            ('sale.sale|sale_exception_fix_cron', "Fix Exception Sales"),
        ]

class Configuration(metaclass=PoolMeta):
    __name__ = 'sale.configuration'

    sale_exception_margin = fields.Integer('Sale exception margin (days)')

class Sale(metaclass=PoolMeta):
    __name__ = 'sale.sale'

    ignored_moves = fields.Function(fields.One2Many('stock.move', None,
        'Ignored Moves'), 'get_ignored_moves')

    @classmethod
    def __setup__(cls):
        super(Sale, cls).__setup__()
        cls._transitions |= set((
                ('confirmed', 'done'),
                ))
        cls._buttons.update({
                'revoke': {
                    'invisible': ~Eval('state').in_(
                        ['confirmed', 'processing']),
                    'depends': ['state'],
                    },
                'create_pending_moves': {
                    'invisible': (~Eval('state').in_(['processing', 'done'])
                        | ~Bool(Eval('ignored_moves', []))),
                    'depends': ['state', 'ignored_moves'],
                    },
                })

    @classmethod
    def get_ignored_moves(cls, sales, name):
        res = dict((x.id, None) for x in sales)
        for sale in sales:
            moves = []
            for line in sale.lines:
                moves += [m.id for m in line.moves_ignored]
            res[sale.id] = moves
        return res

    @classmethod
    @ModelView.button_action('sale_revoke.wizard_revoke')
    def revoke(cls, sales):
        pass

    @classmethod
    def _check_moves(cls, sale):
        moves = []
        for key in [('shipments', 'inventory_moves'),
                ('shipment_returns', 'incoming_moves')]:
            shipments, shipment_moves = key[0], key[1]
            for shipment in getattr(sale, shipments):
                for move in getattr(shipment, shipment_moves):
                    if move.state not in ('cancelled', 'draft', 'done'):
                        moves.append(move)
        return moves

    @classmethod
    def validate_moves(cls, sales):
        for sale in sales:
            moves = cls._check_moves(sale)
            picks = [shipment for shipment in
                list(sale.shipments) + list(sale.shipment_returns)
                if shipment.state not in ('cancelled', 'waiting', 'draft', 'done')]
            if moves or picks:
                names = ', '.join(m.rec_name for m in (moves + picks)[:5])
                if len(moves + picks) > 5:
                    names += '...'
                raise UserError(gettext('sale_revoke.msg_can_not_revoke_moves',
                    record=sale.rec_name, names=names))

    @classmethod
    def validate_invoices(cls, sales):
        for sale in sales:
            invalid_invoices = [invoice for invoice in sale.invoices
                if invoice.state not in ('cancelled', 'draft', 'posted', 'paid')]
            if invalid_invoices:
                names = ', '.join(i.rec_name for i in invalid_invoices[:5])
                if len(invalid_invoices) > 5:
                    names += '...'
                raise UserError(gettext('sale_revoke.msg_can_not_revoke_invoices',
                record=sale.rec_name, names=names))

    @classmethod
    def sale_exception_fix_cron(cls):
        pool = Pool()
        Sale = pool.get('sale.sale')
        Configuration = pool.get('sale.configuration')
        Date = pool.get('ir.date')

        configuration = Configuration.get_singleton()
        margin_days = getattr(configuration, 'sale_exception_margin') or 10
        company = Transaction().context.get('company')

        sales = Sale.search([('company', '=', company),
            ('state', '=', 'processing'),
            ('sale_date', '<=', Date.today()
                - timedelta(days=margin_days)),
            ['OR', ('invoice_state', '=', 'exception'),
                ('shipment_state', '=', 'exception')]],
                order=[('sale_date', 'ASC')])

        for sale in sales:
            cls.__queue__.handle_sale_exception(sale)

    @classmethod
    def handle_sale_exception(cls, sale):

        sale = cls(sale.id)

        try:
            sale.process([sale])
        except Exception as e:
            logger.warning("Skipped process: "+str(sale.id)+", Error: "+str(e))
            return

        sale.validate_moves([sale])
        sale.validate_invoices([sale])

        try:
            sale.handle_shipments([sale])
        except Exception as e:
            logger.warning("Skipped shipment: "+str(sale.id)+", Error: "+str(e))
            return

        try:
            sale.handle_invoices([sale])
        except Exception as e:
            logger.warning("Skipped invoice: "+str(sale.id)+", Error: "+str(e))
            return

    @classmethod
    def handle_shipments(cls, sales):
        pool = Pool()
        Shipment = pool.get('stock.shipment.out')
        ShipmentReturn = pool.get('stock.shipment.out.return')
        HandleShipmentException = pool.get(
            'sale.handle.shipment.exception', type='wizard')

        for sale in sales:
            sale = cls(sale.id)
            Shipment.draft([shipment for shipment in sale.shipments
                if shipment.state == 'waiting'])
            Shipment.cancel([shipment for shipment in sale.shipments
                if shipment.state == 'draft'])
            ShipmentReturn.cancel([shipment for shipment in sale.shipment_returns
                if shipment.state == 'draft'])

            moves = [move for line in sale.lines for move in line.moves
                if move.state == 'cancelled']
            skip = set()
            for line in sale.lines:
                skip |= set(line.moves_ignored + line.moves_recreated)
            pending_moves = [x for x in moves if not x in skip]

            with Transaction().set_context(active_model=cls.__name__,
                    active_ids=[sale.id], active_id=sale.id):
                session_id, _, _ = HandleShipmentException.create()
                handle_shipment_exception = HandleShipmentException(session_id)
                handle_shipment_exception.ask.recreate_moves = []
                handle_shipment_exception.ask.domain_moves = pending_moves
                handle_shipment_exception.transition_handle()
                HandleShipmentException.delete(session_id)

    @classmethod
    def handle_invoices(cls, sales):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        HandleInvoiceException = pool.get(
            'sale.handle.invoice.exception', type='wizard')

        for sale in sales:
            sale = cls(sale.id)
            Invoice.cancel([invoice for invoice in sale.invoices
                if invoice.state == 'draft'])

            cancel_invoices = [invoice for invoice in sale.invoices
                if invoice.state == 'cancelled']
            skip = set(sale.invoices_ignored + sale.invoices_recreated)
            pending_invoices = [i for i in cancel_invoices if not i in skip]

            with Transaction().set_context(active_model=cls.__name__,
                    active_ids=[sale.id], active_id=sale.id):
                session_id, _, _ = HandleInvoiceException.create()
                handle_invoice_exception = HandleInvoiceException(session_id)
                handle_invoice_exception.ask.recreate_invoices = []
                handle_invoice_exception.ask.domain_invoices = pending_invoices
                handle_invoice_exception.transition_handle()
                HandleInvoiceException.delete(session_id)

    @classmethod
    @ModelView.button_action('sale_revoke.act_sale_create_pending_moves_wizard')
    def create_pending_moves(cls, sales):
        pass

class SaleRevokeStart(ModelView):
    'Revoke Start'
    __name__ = 'sale.sale.revoke.start'

    manage_invoices = fields.Boolean('Also Manage Invoices?')

class SaleRevoke(Wizard):
    'Revoke Sales'
    __name__ = 'sale.sale.revoke'

    start = StateView('sale.sale.revoke.start',
        'sale_revoke.sale_revoke_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Revoke', 'revoke', 'tryton-ok', default=True),
            ])

    revoke = StateTransition()

    def transition_revoke(self):
        Sale = Pool().get('sale.sale')

        Sale.validate_moves(self.records)
        if self.start.manage_invoices:
            Sale.validate_invoices(self.records)
            Sale.handle_invoices(self.records)
        Sale.handle_shipments(self.records)

        return 'end'

class SaleCreatePendingMoves(Wizard):
    "Sale Create Pending Moves"
    __name__ = 'sale.sale.create_pending_moves'
    start = StateAction('sale.act_sale_form')

    def do_start(self, action):
        pool = Pool()
        Uom = pool.get('product.uom')
        Sale = pool.get('sale.sale')
        Line = pool.get('sale.line')

        new_sales = []
        for sale in self.records:
            ignored_moves = sale.ignored_moves
            if not ignored_moves:
                continue

            products = dict((move.product.id, 0) for move in ignored_moves)
            sale_units = dict((move.product.id, move.product.sale_uom)
                for move in ignored_moves)

            for move in ignored_moves:
                from_uom = move.unit
                to_uom = move.product.sale_uom
                if from_uom != to_uom:
                    qty = Uom.compute_qty(from_uom, move.quantity,
                        to_uom, round=False)
                else:
                    qty = move.quantity
                products[move.product.id] += qty

            new_sale, = Sale.copy([sale], {'lines': []})

            def default_quantity(data):
                product_id = data.get('product')
                quantity = data.get('quantity')
                if product_id:
                    return products[product_id]
                return quantity

            def default_sale_unit(data):
                product_id = data.get('product')
                unit_id = data.get('unit')
                if product_id:
                    return sale_units[product_id]
                return unit_id

            Line.copy(sale.lines, default={
                'sale': new_sale,
                'quantity': default_quantity,
                'unit': default_sale_unit,
                })

            new_sales.append(new_sale)

        data = {'res_id': [s.id for s in new_sales]}
        if len(new_sales) == 1:
            action['views'].reverse()
        return action, data
