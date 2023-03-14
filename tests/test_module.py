# This file is part sale_purchase_revoke module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.tests.test_tryton import ModuleTestCase


class SalePurchaseRevokeTestCase(ModuleTestCase):
    'Test Sale Purchase Revoke module'
    module = 'sale_purchase_revoke'
    extras = ['sale', 'purchase']

del ModuleTestCase
