# This file is part sale_revoke module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.pool import Pool
from . import sale

def register():
    Pool.register(
        sale.Cron,
        sale.Sale,
        sale.Configuration,
        sale.SaleRevokeStart,
        module='sale_revoke', type_='model')
    Pool.register(
        sale.SaleRevoke,
        sale.SaleCreatePendingMoves,
        module='sale_revoke', type_='wizard')
