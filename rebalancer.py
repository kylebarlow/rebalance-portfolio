#!/usr/bin/env python3

import json
import sys
import os
import copy
import random
import math
import datetime
import tempfile

import numpy as np
import yahoo_fin
import yahoo_fin.stock_info

def truncate(f, n):
    '''Truncates/pads a float f to n decimal places without rounding'''
    s = '{}'.format(f)
    if 'e' in s or 'E' in s:
        return '{0:.{1}f}'.format(f, n)
    i, p, d = s.partition('.')
    return '.'.join([i, (d+'0'*n)[:n]])

def fetch_price(symbol, date_str_format = '%m/%d/%Y %H:%M:%S'):
    cache_path = os.path.join( tempfile.gettempdir(), 'stock_price_cache.json' )
    if os.path.isfile( cache_path ):
        with open(cache_path, 'r') as f:
            price_cache = json.load(f)
    else:
        price_cache = {}

    if symbol not in price_cache or datetime.datetime.now() - datetime.datetime.strptime( price_cache[symbol]['date'], date_str_format) >= datetime.timedelta(minutes=10):
        price_cache[symbol] = {}
        price_cache[symbol]['price'] = yahoo_fin.stock_info.get_live_price(symbol)
        price_cache[symbol]['date'] = datetime.datetime.now().strftime(date_str_format)

    with open(cache_path, 'w') as f:
        json.dump(price_cache, f)

    if price_cache[symbol]['price'] <= 0 or np.isnan(price_cache[symbol]['price']):
        print(price_cache)
        print(symbol)
        assert( price_cache[symbol]['price'] > 0 )
    return price_cache[symbol]['price']

class Holding:
    def __init__ (self, json_holding):
        self.composition = {}
        self.shares = float( json_holding['shares'] )
        if 'buy_additional' in json_holding:
            self.buy_additional = json_holding['buy_additional']
        else:
            self.buy_additional = True
        if 'type' in json_holding:
            assert( 'composition' not in json_holding )
            self.composition[ json_holding['type'] ] = 1.0
        elif 'composition' in json_holding:
            assert( 'type' not in json_holding )
            for t in json_holding['composition']:
                self.composition[t] = json_holding['composition'][t]
        else:
            print( json_holding )
            raise Exception('"Type" or "Composition" is required')
        assert( sum( self.composition.values() ) == 1.0 )

        if self.is_cash_holding():
            self.symbol = 'cash'
            self.current_price = 1.0
        else:
            self.symbol = json_holding['symbol']
            if 'current_price' in json_holding:
                self.current_price = float( json_holding['current_price'] )
            else:
                self.current_price = fetch_price( json_holding['symbol'] )

    def is_cash_holding(self):
        return len(self.composition) == 1 and list(self.composition.keys())[0] == 'cash'

    def buy_shares(self, num_shares):
        self.shares += num_shares

    def sell_shares(self, num_shares):
        self.shares -= num_shares

    @property
    def current_value(self):
        return self.shares * self.current_price

    def get_current_values_by_type(self):
        d = {}
        for t in self.composition:
            d[t] = self.composition[t] * self.current_value
        return d

    @property
    def types(self):
        return sorted( self.composition.keys() )

    def __repr__ (self):
        return_str = 'Symbol: {}\n'.format( self.symbol )
        return_str += 'Composition:\n'
        for t in self.composition:
            return_str += '  {0}: {1:.2f}\n'.format( t, self.composition[t] )
        return_str += 'Shares: {:.1f}\n'.format( self.shares )
        return_str += 'Current price: ${:.2f}\n'.format( self.current_price )
        return_str += 'Current value: ${:.2f}\n'.format( self.current_value )
        if self.buy_additional:
            return_str += 'Buy additional?: Yes\n'
        else:
            return_str += 'Buy additional?: No\n'
        return return_str


class CashHolding(Holding):
    def __init__ (self, starting_value = 0.0):
        self.composition = {'cash' : 1.0}
        self.shares = starting_value
        self.buy_additional = False
        self.symbol = 'cash'
        self.current_price = 1.0

    def add(self, other):
        assert( other.is_cash_holding )
        self.shares += other.shares


class Holdings:
    def __init__ (self, json_holdings):
        self.json_holdings = json_holdings
        self.holdings = []
        self.cash_holding = CashHolding()
        self.holdings.append( self.cash_holding )

        self.symbol_map = {'cash' : self.cash_holding}

        for h in json_holdings:
            holding = Holding(h)
            if holding.is_cash_holding():
                self.cash_holding.add( holding )
            else:
                assert( holding.symbol not in self.symbol_map )
                self.symbol_map[holding.symbol] = holding
                self.holdings.append( holding )

        self.types_to_buy = {}
        for h in self.holdings:
            if h.buy_additional:
                for holding_type in h.types:
                    if holding_type != 'cash' and holding_type != 'other':
                        if holding_type not in self.types_to_buy:
                            self.types_to_buy[holding_type] = []
                        self.types_to_buy[holding_type].append(h)

    def copy (self):
        return Holdings(self.json_holdings)

    @property
    def cash(self):
        return self.cash_holding.shares

    @property
    def current_value(self):
        s = 0.0
        for holding in self.holdings:
            s += holding.current_value
        return s

    def get_current_value_by_type(self):
        dollar_values = {}
        for holding in self.holdings:
            holding_current_values_by_type = holding.get_current_values_by_type()
            for t in holding_current_values_by_type:
                if t not in dollar_values:
                    dollar_values[t] = 0.0
                dollar_values[t] += holding_current_values_by_type[t]
        return dollar_values

    def get_current_allocations(self):
        current_value_by_type = self.get_current_value_by_type()
        current_value = self.current_value
        d = {}
        for t in current_value_by_type:
            d[t] = current_value_by_type[t] / current_value
        return Proportions(d)

    def buy_type(self, type_to_buy, target_allocation, num_shares = 1):
        num_shares = float( num_shares )
        potential_holdings_to_buy = list(self.types_to_buy[type_to_buy])
        holdings_we_can_afford_to_buy = []
        for h in potential_holdings_to_buy:
            new_price = h.current_price * num_shares
            if new_price < self.cash:
                holdings_we_can_afford_to_buy.append( h )

        if len( holdings_we_can_afford_to_buy ) == 0:
            return False

        diffs_after_purchase = []
        for h in holdings_we_can_afford_to_buy:
            h.buy_shares( num_shares )
            new_allocation = self.get_current_allocations().get_type(type_to_buy)
            allocation_diff = abs( new_allocation - target_allocation )
            h.sell_shares( num_shares )
            diffs_after_purchase.append( (allocation_diff, h) )

        if len(diffs_after_purchase) > 0:
            holding_to_buy = diffs_after_purchase[0][1]
            holding_to_buy.buy_shares( num_shares )
            self.cash_holding.sell_shares( holding_to_buy.current_price * num_shares )
            return True
        else:
            return False

    def sell_type(self, type_to_sell, num_shares = 1):
        num_shares = float( num_shares )
        # Note: this should really measure proportions within category somehow
        holding_to_sell = random.choice( list(self.types_to_buy[type_to_sell]) )

        holding_to_sell.sell_shares( num_shares )
        self.cash_holding.buy_shares( holding_to_sell.current_price * num_shares )

    def get_shares_diffs(self, other):
        shares_diffs = []
        for other_holding in other.holdings:
            other_symbol = other_holding.symbol
            if other_symbol not in self.symbol_map:
                shares_diffs.append( (other_holding.shares, other_symbol) )
            else:
                shares_diffs.append( (other_holding.shares - self.symbol_map[other_symbol].shares, other_symbol) )
        return shares_diffs

    def shares_diff(self, other):
        r = ''
        shares_diffs = self.get_shares_diffs(other)
        shares_diffs.sort(reverse = True)
        for shares_diff, symbol in shares_diffs:
            if shares_diff != 0.0:
                if symbol == 'cash':
                    r += '{}: ${}, '.format(symbol, shares_diff)
                else:
                    r += '{}: {}, '.format(symbol, shares_diff)
        return r.strip()[:-1]

    def limit_prices(self, other):
        # Give extra cash to each type of new investment, proportioned based on how much
        # that symbol costs
        shares_diffs = self.get_shares_diffs(other)
        shares_diffs_map = {}
        total_symbol_costs = sum( [self.symbol_map[symbol].current_price for shares_diff, symbol in shares_diffs if symbol != 'cash' and symbol != 'other' and shares_diff != 0.0] )
        shares_proportionality = {}
        for shares_diff, symbol in shares_diffs:
            if symbol != 'cash' and symbol != 'other' and shares_diff > 0:
                shares_proportionality[symbol] = self.symbol_map[symbol].current_price / total_symbol_costs
                shares_diffs_map[symbol] = shares_diff
        limit_prices = []
        for symbol, proportion in shares_proportionality.items():
            limit_prices.append( (proportion * other.cash / shares_diffs_map[symbol] + self.symbol_map[symbol].current_price, symbol) )
        print( 'Limit prices:' )
        for limit_price, symbol in limit_prices:
            print( '{}: {} ({:d} shares)'.format(symbol, truncate(limit_price, 2), math.ceil(shares_diffs_map[symbol])) )
        print()

    def spend_cash_to_balance(self, targets, sell_shares = False):
        new_holdings = self.copy()

        if sell_shares:
            diffs = sorted( [(y, x) for x,y in targets.diff( new_holdings.get_current_allocations() ).items()], reverse = False )
            total_buy_diff = 0.0
            for diff, diff_name in diffs:
                if diff > 0:
                    total_buy_diff += diff

            cash_diff = new_holdings.get_current_allocations().get_type('cash')
            while total_buy_diff > cash_diff:
                diffs = sorted( [(y, x) for x,y in targets.diff( new_holdings.get_current_allocations() ).items()], reverse = False )
                for diff, diff_name in diffs:
                    if diff_name != 'cash':
                        new_holdings.sell_type( diff_name )
                        break
                cash_diff = new_holdings.get_current_allocations().get_type('cash')
            # diffs = sorted( [(y, x) for x,y in targets.diff( new_holdings.get_current_allocations() ).items()], reverse = False )
            # print( diffs )
            # sys.exit()

        while True:
            allocations = new_holdings.get_current_allocations()
            diffs = sorted( [(y, x) for x,y in targets.diff( allocations ).items()], reverse = True )
            purchase_successful = False
            for allocation_diff, type_to_buy in diffs:
                if type_to_buy != 'cash' and type_to_buy != 'other':
                    if new_holdings.buy_type(type_to_buy, targets.get_type(type_to_buy)):
                        purchase_successful = True
                        break
            if not purchase_successful:
                break

        print( 'New shares to buy:' )
        print( self.shares_diff(new_holdings) )

        # Determine limit price
        self.limit_prices( new_holdings )

        print( 'diffs after purchasing:', targets.diff( new_holdings.get_current_allocations() ) )

class Proportions:
    def __init__ (self, proportions):
        self.proportions = proportions

    def items(self):
        return self.proportions.items()

    def get_type(self, t):
        return self.proportions[t]

    def diff(self, other):
        new_proportions_dict = copy.deepcopy(self.proportions)
        for other_type in other.proportions:
            if other_type in new_proportions_dict:
                new_proportions_dict[other_type] -= other.proportions[other_type]
            else:
                new_proportions_dict[other_type] = 0.0 - other.proportions[other_type]
        return Proportions(new_proportions_dict)

    def __repr__ (self):
        r = ''
        for t in sorted(self.proportions.keys()):
            r += "'{0}': {1:.4f}, ".format( t, self.proportions[t] )
        r = r.strip()[:-1]
        return r


class JSONProportions(Proportions):
    def __init__ (self, json_proportions):
        self.proportions = {}
        for holding_type in json_proportions:
            if holding_type == 'stocks':
                assert( 'us_stocks' not in json_proportions )
                assert( 'int_stocks' not in json_proportions )
                self.proportions['us_stocks'] = 0.8* float( json_proportions['stocks'] )
                self.proportions['int_stocks'] = 0.2* float( json_proportions['stocks'] )
            elif holding_type == 'stocks_esg':
                assert( 'us_stocks_esg' not in json_proportions )
                assert( 'int_stocks_esg' not in json_proportions )
                self.proportions['us_stocks_esg'] = 0.8* float( json_proportions['stocks_esg'] )
                self.proportions['int_stocks_esg'] = 0.2* float( json_proportions['stocks_esg'] )
            else:
                self.proportions[holding_type] = float( json_proportions[holding_type] )


def balance_account( json_account, name ):
    targets = JSONProportions( json_account['targets'] )
    print( '\nInitial portfolio: ' + name )
    print( 'targets:', targets )
    holdings = Holdings( json_account['holdings'] )
    print( 'holdings:', holdings.get_current_allocations() )
    print( 'diffs:', targets.diff( holdings.get_current_allocations() ), '\n' )

    holdings.spend_cash_to_balance( targets )


def main():
    accounts = []
    names = []
    for account_file in sys.argv[1:]:
        assert( os.path.isfile(account_file) )
        names.append( os.path.basename(account_file) )
        with open(account_file) as f:
            accounts.append( json.load(f) )

    for account, name in zip(accounts, names):
        balance_account( account, name )

if __name__ == '__main__':
    main()
