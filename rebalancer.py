#!/usr/bin/python3

import json
import sys
import os

class Holding:
    def __init__ (self, json_holding):
        self.symbol = json_holding['symbol']
        self.composition = {}
        self.shares = float( json_holding['shares'] )
        self.current_price = float( json_holding['current_price'] )
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

    @property
    def current_value(self):
        return self.shares * self.current_price

    def get_current_values_by_type(self):
        d = {}
        for t in self.composition:
            d[t] = self.composition[t] * self.current_value
        return d

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


class Holdings:
    def __init__ (self, json_holdings):
        self.holdings = []
        for holding in json_holdings:
            self.holdings.append( Holding( holding ) )

        print( self.get_current_allocations() )

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
        return d


class Targets:
    def __init__ (self, json_targets):
        self.targets = {}
        for holding_type in json_targets:
            if holding_type == 'stocks':
                assert( 'us_stocks' not in json_targets )
                assert( 'int_stocks' not in json_targets )
                self.targets['us_stocks'] = 2.0 * float( json_targets['stocks'] ) / 3.0
                self.targets['int_stocks'] = float( json_targets['stocks'] ) / 3.0
            else:
                self.targets[holding_type] = float( json_targets[holding_type] )

    def __repr__ (self):
        return str( self.targets )


def balance_account( json_account ):
    targets = Targets( json_account['targets'] )
    print( 'targets:', targets )
    holdings = Holdings( json_account['holdings'] )


def main():
    accounts = []
    for account_file in sys.argv[1:]:
        assert( os.path.isfile(account_file) )
        with open(account_file) as f:
            accounts.append( json.load(f) )


    for account in accounts:
        balance_account( account )

if __name__ == '__main__':
    main()
