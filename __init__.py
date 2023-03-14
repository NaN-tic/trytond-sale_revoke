# This file is part sale_purchase_revoke module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.pool import Pool

def register():
    Pool.register(
        module='sale_purchase_revoke', type_='model')
    Pool.register(
        module='sale_purchase_revoke', type_='wizard')
    Pool.register(
        module='sale_purchase_revoke', type_='report')
