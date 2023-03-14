# This file is part sale_purchase_revoke module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.pool import Pool
from . import sale
from . import purchase

def register():
    Pool.register(
        sale.Sale,
        depends=['sale'],
        module='sale_purchase_revoke', type_='model')
    Pool.register(
        sale.SaleCreatePendingMoves,
        depends=['sale'],
        module='sale_purchase_revoke', type_='wizard')
    Pool.register(
        purchase.Purchase,
        depends=['purchase'],
        module='sale_purchase_revoke', type_='model')
    Pool.register(
        purchase.PurchaseCreatePendingMoves,
        depends=['purchase'],
        module='sale_purchase_revoke', type_='wizard')
