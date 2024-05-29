=============
Sale Scenario
=============

Imports::

    >>> import datetime
    >>> from dateutil.relativedelta import relativedelta
    >>> from decimal import Decimal
    >>> from operator import attrgetter
    >>> from proteus import Model, Wizard, Report
    >>> from trytond.tests.tools import activate_modules
    >>> from trytond.modules.company.tests.tools import create_company, \
    ...     get_company
    >>> from trytond.modules.account.tests.tools import create_fiscalyear, \
    ...     create_chart, get_accounts, create_tax
    >>> from trytond.modules.account_invoice.tests.tools import \
    ...     set_fiscalyear_invoice_sequences, create_payment_term
    >>> today = datetime.date.today()

Activate modules::

    >>> config = activate_modules('sale_revoke')

Create company::

    >>> _ = create_company()
    >>> company = get_company()

Create fiscal year::

    >>> fiscalyear = set_fiscalyear_invoice_sequences(
    ...     create_fiscalyear(company))
    >>> fiscalyear.click('create_period')

Create chart of accounts::

    >>> _ = create_chart(company)
    >>> accounts = get_accounts(company)
    >>> revenue = accounts['revenue']
    >>> expense = accounts['expense']
    >>> cash = accounts['cash']

    >>> Journal = Model.get('account.journal')
    >>> PaymentMethod = Model.get('account.invoice.payment.method')
    >>> cash_journal, = Journal.find([('type', '=', 'cash')])
    >>> cash_journal.save()
    >>> payment_method = PaymentMethod()
    >>> payment_method.name = 'Cash'
    >>> payment_method.journal = cash_journal
    >>> payment_method.credit_account = cash
    >>> payment_method.debit_account = cash
    >>> payment_method.save()

Create tax::

    >>> tax = create_tax(Decimal('.10'))
    >>> tax.save()

Create parties::

    >>> Party = Model.get('party.party')
    >>> supplier = Party(name='Supplier')
    >>> supplier.save()
    >>> customer = Party(name='Customer')
    >>> customer.save()

Create account categories::

    >>> ProductCategory = Model.get('product.category')
    >>> account_category = ProductCategory(name="Account Category")
    >>> account_category.accounting = True
    >>> account_category.account_expense = expense
    >>> account_category.account_revenue = revenue
    >>> account_category.save()

    >>> account_category_tax, = account_category.duplicate()
    >>> account_category_tax.customer_taxes.append(tax)
    >>> account_category_tax.save()

Create product::

    >>> ProductUom = Model.get('product.uom')
    >>> unit, = ProductUom.find([('name', '=', 'Unit')])
    >>> ProductTemplate = Model.get('product.template')

    >>> template = ProductTemplate()
    >>> template.name = 'product'
    >>> template.default_uom = unit
    >>> template.type = 'goods'
    >>> template.salable = True
    >>> template.list_price = Decimal('10')
    >>> template.account_category = account_category_tax
    >>> template.save()
    >>> product, = template.products

    >>> template = ProductTemplate()
    >>> template.name = 'service'
    >>> template.default_uom = unit
    >>> template.type = 'service'
    >>> template.salable = True
    >>> template.list_price = Decimal('30')
    >>> template.account_category = account_category
    >>> template.save()
    >>> service, = template.products

Create payment term::

    >>> payment_term = create_payment_term()
    >>> payment_term.save()

Create an Inventory::

    >>> Inventory = Model.get('stock.inventory')
    >>> Location = Model.get('stock.location')
    >>> storage, = Location.find([
    ...         ('code', '=', 'STO'),
    ...         ])
    >>> inventory = Inventory()
    >>> inventory.location = storage
    >>> inventory_line = inventory.lines.new(product=product)
    >>> inventory_line.quantity = 100.0
    >>> inventory_line.expected_quantity = 0.0
    >>> inventory.click('confirm')
    >>> inventory.state
    'done'

Sale 5 products with an invoice method 'on shipment'::

    >>> Sale = Model.get('sale.sale')
    >>> SaleLine = Model.get('sale.line')
    >>> sale = Sale()
    >>> sale.party = customer
    >>> sale.payment_term = payment_term
    >>> sale.invoice_method = 'shipment'
    >>> sale_line = SaleLine()
    >>> sale.lines.append(sale_line)
    >>> sale_line.product = product
    >>> sale_line.quantity = 2.0
    >>> sale_line = SaleLine()
    >>> sale.lines.append(sale_line)
    >>> sale_line.type = 'comment'
    >>> sale_line.description = 'Comment'
    >>> sale_line = SaleLine()
    >>> sale.lines.append(sale_line)
    >>> sale_line.product = product
    >>> sale_line.quantity = 3.0
    >>> sale_line = SaleLine()
    >>> sale.lines.append(sale_line)
    >>> sale_line.product = product
    >>> sale_line.quantity = -3.0
    >>> sale.click('quote')
    >>> sale.click('confirm')
    >>> sale.state
    'processing'
    >>> sale.shipment_state
    'waiting'
    >>> sale.invoice_state
    'none'
    >>> sale.reload()
    >>> len(sale.shipments), len(sale.shipment_returns), len(sale.invoices)
    (1, 1, 0)

Revoke sale and create pending moves::

    >>> revoke_sales = Wizard('sale.sale.revoke', [sale])
    >>> revoke_sales.execute('revoke')
    >>> sale.shipment_state == 'sent'
    True
    >>> shipment, = sale.shipments
    >>> shipment.state == 'cancelled'
    True
    >>> shipment_returns, = sale.shipment_returns
    >>> shipment_returns.state == 'cancelled'
    True

    >>> create_pending_moves = Wizard('sale.sale.create_pending_moves', [sale])
    >>> sales = Sale.find([], order=[('id', 'ASC')])
    >>> len(sales) == 2
    True
    >>> sale1, sale2 = sales
    >>> (sale1.state, sale2.state) == ('done', 'draft')
    True

Sale and partial shipment::

    >>> sale = Sale()
    >>> sale.party = customer
    >>> sale.payment_term = payment_term
    >>> sale.invoice_method = 'shipment'
    >>> sale_line = SaleLine()
    >>> sale.lines.append(sale_line)
    >>> sale_line.product = product
    >>> sale_line.quantity = 10.0
    >>> sale.click('quote')
    >>> sale.click('confirm')
    >>> sale.state
    'processing'
    >>> sale.shipment_state
    'waiting'
    >>> sale.invoice_state
    'none'
    >>> sale.reload()
    >>> len(sale.shipments), len(sale.shipment_returns), len(sale.invoices)
    (1, 0, 0)

Ship 3 products::

    >>> shipment, = sale.shipments
    >>> stock_inventory_move, = shipment.inventory_moves
    >>> stock_inventory_move.quantity
    10.0
    >>> stock_inventory_move.quantity = 3.0
    >>> shipment.click('assign_try')
    >>> shipment.click('pick')
    >>> shipment.click('pack')
    >>> shipment.click('done')
    >>> shipment.state
    'done'

    >>> sale.reload()
    >>> shipments = sale.shipments
    >>> len(shipments) == 2
    True
    >>> shipment1, shipment2 = sale.shipments
    >>> (shipment1.state, shipment2.state) == ('done', 'waiting')
    True
    >>> shipment2.outgoing_moves[0].quantity == 7.0
    True
    >>> sale.invoice_state
    'pending'
    >>> len(sale.shipments), len(sale.shipment_returns), len(sale.invoices)
    (2, 0, 1)
    >>> revoke_sales = Wizard('sale.sale.revoke', [sale])
    >>> revoke_sales.execute('revoke')
    >>> sale.shipment_state == 'sent'
    True
    >>> sale.invoice_state
    'pending'
    >>> len(sale.shipments), len(sale.shipment_returns), len(sale.invoices)
    (2, 0, 1)
    >>> shipment1, shipment2 = sale.shipments
    >>> (shipment1.state, shipment2.state) == ('done', 'cancelled')
    True
    >>> create_pending_moves = Wizard('sale.sale.create_pending_moves', [sale])
    >>> sales = Sale.find([], order=[('id', 'ASC')])
    >>> new_sale = sales[-1]
    >>> new_sale.lines[0].quantity == 7.0
    True

Sale and raise UserError when revoking::

    >>> sale = Sale()
    >>> sale.party = customer
    >>> sale.payment_term = payment_term
    >>> sale.invoice_method = 'shipment'
    >>> sale_line = SaleLine()
    >>> sale.lines.append(sale_line)
    >>> sale_line.product = product
    >>> sale_line.quantity = 10.0
    >>> sale.click('quote')
    >>> sale.click('confirm')
    >>> shipment, = sale.shipments
    >>> shipment.click('assign_try')
    >>> revoke_sales = Wizard('sale.sale.revoke', [sale])
    >>> revoke_sales.execute('revoke') # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
        ...
    trytond.exceptions.UserError:: ...
    >>> revoke_sales.form.manage_invoices = True 
    >>> revoke_sales.execute('revoke') # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
        ...
    trytond.exceptions.UserError:: ...
    >>> sale.reload()
    >>> sale.shipment_state == 'waiting'
    True
