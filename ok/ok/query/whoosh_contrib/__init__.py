# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function, absolute_import

"""
Package for whoosh implementation of find queries. Details of implementation are mostly hidden inside this package.
All interface must be used from query.find module and no direction calls here outside.
Main idea that whoosh might be replaced by other IR engine implementations later if it wont have acceptable performance
"""
