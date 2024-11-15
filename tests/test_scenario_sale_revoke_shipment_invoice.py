import unittest
from decimal import Decimal

from proteus import Model, Wizard
from trytond.exceptions import UserError
from trytond.modules.account.tests.tools import (create_chart,
                                                 create_fiscalyear, create_tax,
                                                 get_accounts)
from trytond.modules.account_invoice.tests.tools import (
    create_payment_term, set_fiscalyear_invoice_sequences)
from trytond.modules.company.tests.tools import create_company, get_company
from trytond.tests.test_tryton import drop_db
from trytond.tests.tools import activate_modules


class Test(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):

        # Imports

        # Activate modules
        activate_modules('sale_revoke')

        # Create company
        _ = create_company()
        company = get_company()

        # Create fiscal year
        fiscalyear = set_fiscalyear_invoice_sequences(
            create_fiscalyear(company))
        fiscalyear.click('create_period')

        # Create chart of accounts
        _ = create_chart(company)
        accounts = get_accounts(company)
        revenue = accounts['revenue']
        expense = accounts['expense']
        cash = accounts['cash']
        Journal = Model.get('account.journal')
        PaymentMethod = Model.get('account.invoice.payment.method')
        cash_journal, = Journal.find([('type', '=', 'cash')])
        cash_journal.save()
        payment_method = PaymentMethod()
        payment_method.name = 'Cash'
        payment_method.journal = cash_journal
        payment_method.credit_account = cash
        payment_method.debit_account = cash
        payment_method.save()

        # Create tax
        tax = create_tax(Decimal('.10'))
        tax.save()

        # Create parties
        Party = Model.get('party.party')
        supplier = Party(name='Supplier')
        supplier.save()
        customer = Party(name='Customer')
        customer.save()

        # Create account categories
        ProductCategory = Model.get('product.category')
        account_category = ProductCategory(name="Account Category")
        account_category.accounting = True
        account_category.account_expense = expense
        account_category.account_revenue = revenue
        account_category.save()
        account_category_tax, = account_category.duplicate()
        account_category_tax.customer_taxes.append(tax)
        account_category_tax.save()

        # Create product
        ProductUom = Model.get('product.uom')
        unit, = ProductUom.find([('name', '=', 'Unit')])
        ProductTemplate = Model.get('product.template')
        template = ProductTemplate()
        template.name = 'product'
        template.default_uom = unit
        template.type = 'goods'
        template.salable = True
        template.list_price = Decimal('10')
        template.account_category = account_category_tax
        template.save()
        product, = template.products
        template = ProductTemplate()
        template.name = 'service'
        template.default_uom = unit
        template.type = 'service'
        template.salable = True
        template.list_price = Decimal('30')
        template.account_category = account_category
        template.save()
        service, = template.products

        # Create payment term
        payment_term = create_payment_term()
        payment_term.save()

        # Create an Inventory
        Inventory = Model.get('stock.inventory')
        Location = Model.get('stock.location')
        storage, = Location.find([
            ('code', '=', 'STO'),
        ])
        inventory = Inventory()
        inventory.location = storage
        inventory_line = inventory.lines.new(product=product)
        inventory_line.quantity = 100.0
        inventory_line.expected_quantity = 0.0
        inventory.click('confirm')
        self.assertEqual(inventory.state, 'done')

        # Sale 5 products and revoke sales managing shipments and invoices
        Sale = Model.get('sale.sale')
        SaleLine = Model.get('sale.line')
        sale = Sale()
        sale.party = customer
        sale.payment_term = payment_term
        sale.invoice_method = 'shipment'
        sale_line = SaleLine()
        sale.lines.append(sale_line)
        sale_line.product = product
        sale_line.quantity = 2.0
        sale_line = SaleLine()
        sale.lines.append(sale_line)
        sale_line.type = 'comment'
        sale_line.description = 'Comment'
        sale_line = SaleLine()
        sale.lines.append(sale_line)
        sale_line.product = product
        sale_line.quantity = 3.0
        sale.click('quote')
        sale.click('confirm')
        self.assertEqual(sale.state, 'processing')
        self.assertEqual(sale.shipment_state, 'waiting')
        self.assertEqual(sale.invoice_state, 'none')
        sale.reload()
        self.assertEqual(len(sale.shipments), 1)

        self.assertEqual(len(sale.shipment_returns), 0)

        self.assertEqual(len(sale.invoices), 0)

        # Not yet linked to invoice lines
        shipment, = sale.shipments
        stock_move1, stock_move2 = sorted(shipment.outgoing_moves,
                                          key=lambda m: m.quantity or 0)
        self.assertEqual(len(stock_move1.invoice_lines), 0)
        self.assertEqual(len(stock_move2.invoice_lines), 0)

        # Validate Shipments
        shipment.click('assign_try')
        shipment.click('pick')
        shipment.click('pack')
        shipment.click('do')

        # Revoke sales with manage invoices
        self.assertEqual(sale.invoice_state, 'pending')
        self.assertEqual(len(sale.shipments), 1)

        self.assertEqual(len(sale.shipment_returns), 0)

        self.assertEqual(len(sale.invoices), 0)
        revoke_sales = Wizard('sale.sale.revoke', [sale])
        revoke_sales.form.manage_invoices = True
        revoke_sales.execute('revoke')
        self.assertEqual(sale.shipment_state, 'sent')
        self.assertEqual(sale.invoice_state, 'none')
        self.assertEqual(len(sale.shipments), 1)

        self.assertEqual(len(sale.shipment_returns), 0)

        self.assertEqual(len(sale.invoices), 1)
        self.assertEqual(sale.invoices[0].state, 'cancelled')

        # Open customer invoice
        sale.reload()
        self.assertEqual(sale.invoice_state, 'none')
        invoice, = sale.invoices
        self.assertEqual(invoice.type, 'out')
        invoice_line1, invoice_line2 = sorted(invoice.lines,
                                              key=lambda l: l.quantity or 0)
        # Invoice lines must be linked to each stock moves
        self.assertEqual(invoice_line1.stock_moves, [stock_move1])
        self.assertEqual(invoice_line2.stock_moves, [stock_move2])

        # Sale and raise UserError when revoking
        sale = Sale()
        sale.party = customer
        sale.payment_term = payment_term
        sale.invoice_method = 'shipment'
        sale_line = SaleLine()
        sale.lines.append(sale_line)
        sale_line.product = product
        sale_line.quantity = 10.0
        sale.click('quote')
        sale.click('confirm')
        shipment, = sale.shipments
        shipment.click('assign_try')
        revoke_sales = Wizard('sale.sale.revoke', [sale])
        with self.assertRaises(UserError):
            revoke_sales.execute('revoke')
        revoke_sales.form.manage_invoices = True
        with self.assertRaises(UserError):
            revoke_sales.execute('revoke')
        sale.reload()
        self.assertEqual(sale.shipment_state, 'waiting')
